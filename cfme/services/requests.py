# -*- coding: utf-8 -*-
from navmazing import NavigateToAttribute, NavigateToSibling
from widgetastic.widget import Text, Table, Checkbox, View
from widgetastic_manageiq import BreadCrumb, SummaryForm, SummaryFormItem, PaginationPane, Button
from widgetastic_patternfly import Input, Tab, BootstrapTreeview, FlashMessages

from cfme.base.login import BaseLoggedInPage
from cfme.common.vm_views import ProvisionView, BasicProvisionFormView
from cfme.exceptions import RequestException, ItemNotFound
from utils.log import logger
from utils.appliance import Navigatable
from utils.appliance.implementations.ui import navigator, CFMENavigateStep, navigate_to
from utils.varmeth import variable
from utils.wait import wait_for


class Request(Navigatable):
    """
    Class describes request row from Services - Requests page
    """

    REQUEST_FINISHED_STATES = {'Migrated', 'Finished'}

    def __init__(self, description=None, cells=None, partial_check=False, appliance=None):
        """
        Args:
            description: by default we'll be checking Description column to find required row
            cells: cells used to find required row in table
            partial_check: greedy search or not?
        """
        Navigatable.__init__(self, appliance=appliance)
        self.description = description
        self.partial_check = partial_check
        self.cells = cells or {'Description': self.description}
        self.row = None

    # TODO Replace varmeth with Sentaku one day
    @variable(alias='rest')
    def wait_for_request(self):
        def _finished():
            self.rest.reload()
            return self.rest.request_state.title() in self.REQUEST_FINISHED_STATES

        wait_for(_finished, num_sec=800, delay=20, message="Request finished")

    @wait_for_request.variant('ui')
    def wait_for_request_ui(self):
        def _finished():
            self.update(method='ui')
            return self.row.request_state.text in self.REQUEST_FINISHED_STATES

        wait_for(_finished, num_sec=800, delay=20, message="Request finished")

    @property
    def rest(self):
        if self.partial_check:
            matching_requests = self.appliance.rest_api.collections.requests.find_by(
                description='%{}%'.format(self.cells['Description']))
        else:
            matching_requests = self.appliance.rest_api.collections.requests.find_by(
                description=self.cells['Description'])
        if len(matching_requests) > 1:
            raise RequestException(
                'Multiple requests with matching \"{}\" '
                'found - be more specific!'.format(
                    self.description))
        elif len(matching_requests) == 0:
            raise ItemNotFound(
                'Nothing matching "{}" with partial_check={} was found'.format(
                    self.cells['Description'], self.partial_check))
        else:
            self.description = matching_requests[0].description
            return matching_requests[0]

    def get_request_row_from_ui(self):
        """Opens CFME UI and return table_row object"""
        view = navigate_to(self, 'All')
        self.row = view.find_request(self.rest.description, partial_check=False)
        return self.row

    def get_request_id(self):
        return self.rest.request_id

    @variable(alias='rest')
    def exists(self):
        """If our Request exists in CFME"""
        try:
            return self.rest.exists
        except ItemNotFound:
            return False

    @property
    def status(self):
        self.update()
        return self.rest.status

    @property
    def request_state(self):
        self.update()
        return self.rest.request_state

    @exists.variant('ui')
    def exists_ui(self):
        """
        Checks if Request if shown in CFME UI.
        Request might be removed from CFME UI but present in DB

        """
        view = navigate_to(self, 'All')
        return bool(view.find_request(self.cells, self.partial_check))

    @variable(alias='rest')
    def update(self):
        """Updates Request object details - last message, status etc
        """
        self.rest.reload()
        self.description = self.rest.description
        self.cells = {'Description': self.description}

    @update.variant('ui')
    def update_ui(self):
        view = navigate_to(self, 'All')
        view.reload.click()
        self.row = view.find_request(cells=self.cells, partial_check=self.partial_check)

    @variable(alias='rest')
    def approve_request(self, reason):
        """Approves request with specified reason
        Args:
            reason: Reason for approving the request.
            cancel: Whether to cancel the approval.
        """
        self.rest.action.approve(reason=reason)

    @approve_request.variant('ui')
    def approve_request_ui(self, reason, cancel=False):
        view = navigate_to(self, 'Approve')
        view.reason.fill(reason)
        if not cancel:
            view.submit.click()
        else:
            view.breadcrumb.click_location(view.breadcrumb.locations[1], handle_alert=True)
        view.flash.assert_no_error()

    @variable(alias='rest')
    def deny_request(self, reason):
        """Opens the specified request and deny it.
        Args:
            reason: Reason for denying the request.
            cancel: Whether to cancel the denial.
        """
        self.rest.action.deny(reason=reason)

    @deny_request.variant('ui')
    def deny_request_ui(self, reason, cancel=False):
        view = navigate_to(self, 'Deny')
        view.reason.fill(reason)
        if not cancel:
            view.submit.click()
        else:
            view.breadcrumb.click_location(view.breadcrumb.locations[1], handle_alert=True)
        view.flash.assert_no_error()

    def remove_request(self, cancel=False):
        """Opens the specified request and deletes it - removes from UI
        Args:
            cancel: Whether to cancel the deletion.
        """
        view = navigate_to(self, 'Details')
        view.toolbar.delete.click()
        view.browser.handle_alert(cancel=cancel, wait=10.0)
        view.browser.plugin.ensure_page_safe()

    @variable(alias='rest')
    def is_finished(self):
        """Helper function checks if a request is completed
        """
        self.update()
        return self.rest.request_state.title() in self.REQUEST_FINISHED_STATES

    @is_finished.variant('ui')
    def is_finished_ui(self):
        self.update(method='ui')
        return self.row.request_state.text in self.REQUEST_FINISHED_STATES

    @variable(alias='rest')
    def is_succeeded(self):
        return self.is_finished() and self.rest.status.title() == 'Ok'

    @is_succeeded.variant('ui')
    def is_succeeded_ui(self):
        return self.is_finished(method=('ui')) and self.row.status.text == 'Ok'

    def copy_request(self, values=None, cancel=False):
        """Copies the request  and edits if needed
        """
        view = navigate_to(self, 'Copy')
        view.form.fill(values)
        if not cancel:
            view.form.submit_button.click()
        else:
            view.cancel_button.click()
        view.flash.assert_no_error()
        # The way we identify request is a description which is based on vm_name,
        # no need returning Request obj if name is the same => raw request copy
        if 'vm_name' in values.keys():
            return Request(description=values['vm_name'], partial_check=True)

    def edit_request(self, values, cancel=False):
        """Opens the request for editing and saves or cancels depending on success.
        """
        view = navigate_to(self, 'Edit')
        if view.form.fill(values):
            if not cancel:
                view.form.submit_button.click()
                self.update()
            else:
                view.cancel_button.click()
        else:
            logger.debug('Nothing was changed in current request')
        view.flash.assert_no_error()


class RequestBasicView(BaseLoggedInPage):
    title = Text('//div[@id="main-content"]//h1')
    reload = Button(title='Reload the current display')

    @property
    def in_requests(self):
        return self.logged_in_as_current_user
        # TODO uncomment after BZ 1472844 is fixed
        # and  self.navigation.currently_selected == ['Services', 'Requests'] and


class RequestsView(RequestBasicView):
    table = Table(locator='//*[@id="list_grid"]/table')
    paginator = PaginationPane()
    flash = FlashMessages('.//div[@id="flash_msg_div"]')

    def find_request(self, cells, partial_check=False):
        """Finds the request and returns the row element
        Args:
            cells: Search data for the requests table.
            partial_check: If to use the ``__contains`` operator
        Returns: row
        """
        contains = '' if not partial_check else '__contains'
        column_list = self.table.attributized_headers
        for key in cells.keys():
            for column_name, column_text in column_list.items():
                if key == column_text:
                    cells['{}{}'.format(column_name, contains)] = cells.pop(key)
                    break

        # TODO Replace Paginator with paginator_pane after 1450002 gets resolved
        from cfme.web_ui import paginator
        for page in paginator.pages():
            rows = list(self.table.rows(**cells))
            if len(rows) == 0:
                # row not on this page, assume it has yet to appear
                # it might be nice to add an option to fail at this point
                continue
            elif len(rows) > 1:
                raise RequestException(
                    'Multiple requests with matching content found - be more specific!')
            else:
                # found the row!
                row = rows[0]
                logger.debug(' Request Message: %s', row.last_message.text)
                return row
        else:
            raise Exception("The requst specified by {} not found!".format(str(cells)))

    @property
    def is_displayed(self):
        return self.in_requests and self.title.text == 'Requests'


class RequestDetailsToolBar(RequestsView):
    copy = Button(title='Copy original Request')
    edit = Button(title='Edit the original Request')
    delete = Button(title='Delete this Request')
    approve = Button(title='Approve this Request')
    deny = Button(title='Deny this Request')


class RequestDetailsView(RequestsView):

    @View.nested
    class details(View):  # noqa
        request_details = SummaryForm('Request Details')

    @View.nested
    class request(Tab):  # noqa
        TAB_NAME = 'Request'
        email = SummaryFormItem('Request Information', 'E-Mail')
        first_name = SummaryFormItem('Request Information', 'First Name')
        last_name = SummaryFormItem('Request Information', 'Last Name')
        notes = SummaryFormItem('Request Information', 'Notes')
        manager_name = SummaryFormItem('Manager', 'Name')

    @View.nested
    class purpose(Tab):  # noqa
        TAB_NAME = 'Purpose'
        apply_tags = BootstrapTreeview('all_tags_treebox')

    @View.nested
    class catalog(Tab):  # noqa
        TAB_NAME = 'Catalog'
        filter_template = SummaryFormItem('Select', 'Filter')
        name = SummaryFormItem('Select', 'Name')
        provision_type = SummaryFormItem('Select', 'Provision Type')
        linked_clone = Checkbox(id='service__linked_clone')
        vm_count = SummaryFormItem('Number of VMs', 'Count')
        instance_count = SummaryFormItem('Number of Instances', 'Count')
        vm_name = SummaryFormItem('Naming', 'VM Name')
        instance_name = SummaryFormItem('Naming', 'Instance Name')
        vm_description = SummaryFormItem('Naming', 'VM Description')

    @View.nested
    class environment(Tab):  # noqa
        TAB_NAME = 'Environment'

        automatic_placement = Checkbox(name='environment__placement_auto')
        # Azure
        virtual_private_cloud = SummaryFormItem('Placement - Options', 'Virtual Private Cloud')
        cloud_subnet = SummaryFormItem('Placement - Options', 'Cloud Subnet')
        security_groups = SummaryFormItem('Placement - Options', 'Security Groups')
        resource_groups = SummaryFormItem('Placement - Options', 'Resource Groups')
        public_ip_address = SummaryFormItem('Placement - Options', 'Public IP Address ')
        # GCE
        availability_zone = SummaryFormItem('Placement - Options', 'Availability Zones')
        cloud_network = SummaryFormItem('Placement - Options', 'Cloud Network')
        # Infra
        datacenter = SummaryFormItem('Datacenter', 'Name')
        cluster = SummaryFormItem('Cluster', 'Name')
        resource_pool = SummaryFormItem('Resource Pool', 'Name')
        folder = SummaryFormItem('Folder', 'Name')
        host_filter = SummaryFormItem('Host', 'Filter')
        host_name = SummaryFormItem('Host', 'Name')
        datastore_storage_profile = SummaryFormItem('Datastore', 'Storage Profile')
        datastore_filter = SummaryFormItem('Datastore', 'Filter')
        datastore_name = SummaryFormItem('Datastore', 'Name')

    @View.nested
    class hardware(Tab):  # noqa
        num_cpus = SummaryFormItem('Hardware', 'Number of CPUS')
        memory = SummaryFormItem('Hardware', 'Startup Memory (MB)')
        dynamic_memory = SummaryFormItem('Hardware', 'Dynamic Memory')
        vm_limit_cpu = SummaryFormItem('VM Limits', 'CPU (%)')
        vm_reserve_cpu = SummaryFormItem('VM Reservations', 'CPU (%)')

    @View.nested
    class network(Tab):  # noqa
        vlan = SummaryFormItem('Network Adapter Information', 'vLan')

    @View.nested
    class properties(Tab):  # noqa
        instance_type = SummaryFormItem('Properties', 'Instance Type')
        boot_disk_size = SummaryFormItem('Properties', 'Boot Disk Size ')
        is_preemtible = Checkbox(name='hardware__is_preemptible')

    @View.nested
    class customize(Tab):  # noqa
        username = SummaryFormItem('Credentials', 'Username')
        ip_mode = SummaryFormItem('IP Address Information', 'Address Mode')
        hostname = SummaryFormItem('IP Address Information', 'Address Mode')
        subnet_mask = SummaryFormItem('IP Address Information', 'Subnet Mask')
        gateway = SummaryFormItem('IP Address Information', 'Gateway')
        dns_server_list = SummaryFormItem('DNS', 'DNS Server list')
        dns_suffix_list = SummaryFormItem('DNS', 'DNS Suffix list')
        subnet_mask = SummaryFormItem('IP Address Information', 'Subnet Mask')
        customize_template = SummaryFormItem('Customize Template', 'Script Name')

    @View.nested
    class schedule(Tab):  # noqa
        when_provision = SummaryFormItem('Schedule Info', 'When to Provision')
        stateless = Checkbox(name='shedule__stateless')
        power_on = SummaryFormItem('Lifespan', 'Power on virtual machines after creation')
        retirement = SummaryFormItem('Lifespan', 'Time until Retirement')
        retirement_warning = SummaryFormItem('Lifespan', 'Retirement Warning')

    @property
    def is_displayed(self):
        return (self.in_requests and
                self.title.text == self.context['object'].rest.description)

    breadcrumb = BreadCrumb()
    toolbar = RequestDetailsToolBar()


class RequestApprovalView(RequestDetailsView):

    reason = Input(name='reason')
    submit = Button(title='Submit')
    cancel = Button(title="Cancel this provisioning request")

    @property
    def is_displayed(self):
        try:
            return (
                self.breadcrumb.locations[1] == self.context['object'].rest.description and
                self.breadcrumb.locations[2] == 'Request Approval')
        except Exception:
            return False


class RequestDenialView(RequestDetailsView):

    reason = Input(name='reason')
    submit = Button(title='Submit')
    cancel = Button(title="Cancel this provisioning request")

    @property
    def is_displayed(self):
        try:
            return (
                self.breadcrumb.locations[1] == self.context['object'].rest.description and
                self.breadcrumb.locations[2] == 'Request Denial')
        except Exception:
            return False


class RequestProvisionView(ProvisionView):

    @View.nested
    class form(BasicProvisionFormView):  # noqa
        submit_button = Button('Submit')  # Submit for 2nd page, tabular form
        cancel_button = Button('Cancel')

    @property
    def is_displayed(self):
        try:
            return self.breadcrumb.locations[1] == self.context['object'].rest.description
        except Exception:
            return False


class RequestEditView(RequestProvisionView):

    @property
    def is_displayed(self):
        try:
            return (
                self.breadcrumb.locations[1] == self.context['object'].rest.description and
                self.breadcrumb.locations[2] == 'Edit VM Provision')
        except Exception:
            return False


class RequestCopyView(RequestProvisionView):

    @property
    def is_displayed(self):
        try:
            return (
                self.breadcrumb.locations[1] == self.context['object'].rest.description and
                self.breadcrumb.locations[2] == 'Copy of VM Provision Request')
        except Exception:
            return False


@navigator.register(Request, 'All')
class RequestAll(CFMENavigateStep):
    VIEW = RequestsView
    prerequisite = NavigateToAttribute('appliance.server', 'LoggedIn')

    def step(self, *args, **kwargs):
        self.prerequisite_view.navigation.select('Services', 'Requests')


@navigator.register(Request, 'Details')
class RequestDetails(CFMENavigateStep):
    VIEW = RequestDetailsView
    prerequisite = NavigateToSibling('All')

    def step(self, *args, **kwargs):
        try:
            return self.prerequisite_view.table.row(description=self.obj.rest.description).click()
        except (NameError, TypeError):
            logger.warning('Exception caught, could not match Request')


@navigator.register(Request, 'Edit')
class EditRequest(CFMENavigateStep):
    VIEW = RequestEditView
    prerequisite = NavigateToSibling('Details')

    def step(self):
        return self.prerequisite_view.toolbar.edit.click()


@navigator.register(Request, 'Copy')
class CopyRequest(CFMENavigateStep):
    VIEW = RequestCopyView
    prerequisite = NavigateToSibling('Details')

    def step(self):
        return self.prerequisite_view.toolbar.copy.click()


@navigator.register(Request, 'Approve')
class ApproveRequest(CFMENavigateStep):
    VIEW = RequestApprovalView
    prerequisite = NavigateToSibling('Details')

    def step(self):
        return self.prerequisite_view.toolbar.approve.click()


@navigator.register(Request, 'Deny')
class DenyRequest(CFMENavigateStep):
    VIEW = RequestDenialView
    prerequisite = NavigateToSibling('Details')

    def step(self):
        return self.prerequisite_view.toolbar.deny.click()
