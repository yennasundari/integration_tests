"""Tests for Openstack cloud volume Backups"""

import fauxfactory
import pytest

from cfme.cloud.provider.openstack import OpenStackProvider
from cfme.utils.appliance.implementations.ui import navigate_to
from cfme.utils.log import logger
from cfme.utils.wait import wait_for, wait_for_decorator

pytestmark = [
    pytest.mark.usefixtures("setup_provider"),
    pytest.mark.provider([OpenStackProvider])
]

VOLUME_SIZE = 1


@pytest.fixture(scope='function')
def volume_backup(appliance, provider):
    volume_collection = appliance.collections.volumes
    storage_manager = '{} Cinder Manager'.format(provider.name)
    backup_collection = appliance.collections.volume_backups.filter({'provider': provider})

    # create new volume
    volume = volume_collection.create(name=fauxfactory.gen_alpha(),
                                      storage_manager=storage_manager,
                                      tenant=provider.data['provisioning']['cloud_tenant'],
                                      size=VOLUME_SIZE,
                                      provider=provider)

    # create new backup for crated volume
    if volume.status == 'available':
        backup_name = fauxfactory.gen_alpha()
        volume.create_backup(backup_name)
        volume_backup = backup_collection.instantiate(backup_name, provider)
        yield volume_backup
    else:
        pytest.skip('Skipping volume backup tests, provider side volume creation fails')

    try:
        if volume_backup.exists:
            backup_collection.delete(volume_backup, wait=False)
        if volume.exists:
            volume.delete(wait=False)
    except Exception:
        logger.warning('Exception during volume deletion - skipping..')


@pytest.fixture(scope='function')
def volume_backup_with_type(appliance, provider):
    vol_type = provider.mgmt.capi.volume_types.create(name=fauxfactory.gen_alpha())
    volume_type = appliance.collections.volume_types.instantiate(vol_type.name, provider)

    @wait_for_decorator(delay=10, timeout=300,
                        message="Waiting for volume type to appear")
    def volume_type_is_displayed():
        volume_type.refresh()
        return volume_type.exists

    volume_collection = appliance.collections.volumes
    storage_manager = '{} Cinder Manager'.format(provider.name)
    backup_collection = appliance.collections.volume_backups.filter({'provider': provider})

    # create new volume
    volume = volume_collection.create(name=fauxfactory.gen_alpha(),
                                      storage_manager=storage_manager,
                                      tenant=provider.data['provisioning']['cloud_tenant'],
                                      volume_type=volume_type.name,
                                      size=VOLUME_SIZE,
                                      provider=provider)

    # create new backup for crated volume
    if volume.status == 'available':
        backup_name = fauxfactory.gen_alpha()
        volume.create_backup(backup_name)
        volume_backup = backup_collection.instantiate(backup_name, provider)
        yield volume_backup
    else:
        pytest.skip('Skipping volume backup tests, provider side volume creation fails')


    if volume_backup.exists:
        backup_collection.delete(volume_backup)

    if volume.exists:
        volume.delete(wait=False)

    if volume_type.exists:
        provider.mgmt.capi.volume_types.delete(vol_type)


@pytest.fixture(scope='function')
def incremental_backup(volume_backup, provider):
    backup_collection = provider.appliance.collections.volume_backups.filter({'provider': provider})
    volume = volume_backup.appliance.collections.volumes.instantiate(volume_backup.volume, provider)

    # create incremental backup for a volume with existing backup
    if volume.status == 'available':
        backup_name = fauxfactory.gen_alpha()
        volume.create_backup(backup_name, incremental=True)
        incremental_backup = backup_collection.instantiate(backup_name, provider)
        yield incremental_backup
    else:
        pytest.skip('Skipping incremental backup fixture: volume not available')


    try:
        if incremental_backup.exists:
            backup_collection.delete(incremental_backup)
    except Exception:
        logger.warning('Exception during volume backup deletion - skipping..')


@pytest.fixture(scope='function')
def new_instance(provider):
    instance_name = fauxfactory.gen_alpha()
    collection = provider.appliance.provider_based_collection(provider)
    instance = collection.create_rest(instance_name, provider)
    yield instance

    instance.cleanup_on_provider()


@pytest.fixture(scope='function')
def attached_volume(appliance, provider, volume_backup, new_instance):
    attached_volume = appliance.collections.volumes.instantiate(volume_backup.volume, provider)
    initial_volume_count = new_instance.volume_count
    new_instance.attach_volume(attached_volume.name)

    @wait_for_decorator(delay=10, timeout=300,
                        message="Waiting for volume to be attached to instance")
    def volume_attached_to_instance():
        new_instance.refresh_relationships()
        return new_instance.volume_count > initial_volume_count

    yield attached_volume

    new_instance.detach_volume(attached_volume.name)

    @wait_for_decorator(delay=10, timeout=300,
                        message="Waiting for volume to be detached from instance")
    def volume_detached_from_instance():
        new_instance.refresh_relationships()
        return new_instance.volume_count == initial_volume_count


@pytest.mark.rfe
def test_create_volume_backup(volume_backup):
    assert volume_backup.exists
    assert volume_backup.size == VOLUME_SIZE


@pytest.mark.rfe
def test_create_volume_incremental_backup(incremental_backup):
    assert incremental_backup.exists
    assert incremental_backup.size == VOLUME_SIZE


@pytest.mark.rfe
def test_incr_backup_of_attached_volume_crud(appliance, provider, request, attached_volume):
    backup_name = fauxfactory.gen_alpha()
    collection = appliance.collections.volume_backups.filter({'provider': provider})
    attached_volume.create_backup(backup_name, incremental=True, force=True)
    incr_backup_of_attached_volume = collection.instantiate(backup_name, provider)

    @request.addfinalizer
    def cleanup():
        if incr_backup_of_attached_volume.exists:
            collection.delete(incr_backup_of_attached_volume, wait=False)

    assert incr_backup_of_attached_volume.exists
    assert incr_backup_of_attached_volume.size == VOLUME_SIZE

    collection.delete(incr_backup_of_attached_volume, wait=False)
    view = navigate_to(collection, "All")

    view.flash.assert_success_message(
        'Delete of Backup "{}" was successfully initiated.'.format(backup_name))

    wait_for(lambda: not incr_backup_of_attached_volume.exists, delay=5, timeout=600,
             fail_func=incr_backup_of_attached_volume.refresh,
             message='Wait for Backup to disappear')



@pytest.mark.rfe
@pytest.mark.ignore_stream('5.9')
def test_create_backup_of_volume_with_type(volume_backup_with_type):
    assert volume_backup_with_type.exists
    assert volume_backup_with_type.size == VOLUME_SIZE


@pytest.mark.rfe
def test_restore_volume_backup(volume_backup):
    if volume_backup.status == 'available':
        volume_backup.restore(volume_backup.volume)
    else:
        pytest.skip('Skipping restore volume backup test, volume backup is not available')


@pytest.mark.rfe
def test_restore_incremental_backup(incremental_backup):
    if incremental_backup.status == 'available':
        incremental_backup.restore(incremental_backup.volume)
    else:
        pytest.skip('Skipping restore incremental backup test, volume backup is not available')
