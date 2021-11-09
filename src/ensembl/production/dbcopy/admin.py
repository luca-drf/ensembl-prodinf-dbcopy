#   See the NOTICE file distributed with this work for additional information
#   regarding copyright ownership.
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#       http://www.apache.org/licenses/LICENSE-2.0
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
from django.contrib import admin, messages
from django.contrib.admin.utils import model_ngettext
from django.core.exceptions import ValidationError
from django.db.models import F, Q, Count
from django.db.models.query import QuerySet
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django_admin_inline_paginator.admin import TabularInlinePaginated
from ensembl.production.djcore.admin import SuperUserAdmin
from ensembl.production.dbcopy.filters import DBCopyUserFilter, OverallStatusFilter

from ensembl.production.dbcopy.forms import RequestJobForm, GroupInlineForm
from ensembl.production.dbcopy.models import Host, RequestJob, HostGroup, TargetHostGroup, TransferLog


class GroupInline(admin.TabularInline):
    model = HostGroup
    extra = 1
    form = GroupInlineForm
    fields = ('group_name',)
    verbose_name = "HostGroup restriction"
    verbose_name_plural = "HostGroup restrictions"


@admin.register(TargetHostGroup)
class TargetHostGroupAdmin(admin.ModelAdmin, SuperUserAdmin):
    list_display = ('target_group_name', 'get_hosts')
    fields = ('target_group_name', 'target_host')
    search_fields = ('target_group_name', 'target_host__name')

    def get_hosts(self, obj):
        return ", ".join([str(g) for g in obj.target_host.all()])


class TargetGroupInline(admin.TabularInline):
    model = TargetHostGroup.target_host.through


@admin.register(Host)
class HostItemAdmin(admin.ModelAdmin, SuperUserAdmin):
    class Media:
        css = {
            'all': ('dbcopy/css/db_copy.css',)
        }

    # form = HostRecordForm
    inlines = (GroupInline, TargetGroupInline)
    list_display = ('name', 'port', 'mysql_user', 'virtual_machine', 'mysqld_file_owner', 'get_target_groups', 'active')
    fields = ('name', 'port', 'mysql_user', 'virtual_machine', 'mysqld_file_owner', 'active')
    search_fields = ('name', 'port', 'mysql_user', 'virtual_machine', 'mysqld_file_owner', 'active')

    def get_target_groups(self, obj):
        return ", ".join([str(each_group.target_group_name)
                          for each_group in TargetHostGroup.objects.filter(target_host__auto_id=obj.auto_id)
                          ])

    get_target_groups.short_description = 'Host Target Groups '


class TransferLogInline(TabularInlinePaginated):
    model = TransferLog
    template = "admin/ensembl_dbcopy/edit_inline/tabular_paginated.html"
    per_page = 15
    fields = ('table_schema', 'table_name', 'renamed_table_schema', 'start_date', 'end_date', 'table_status')
    readonly_fields = ('table_schema', 'table_name', 'renamed_table_schema', 'start_date', 'end_date', 'table_status')
    can_delete = False
    ordering = F('end_date').asc(nulls_first=True), F('auto_id')

    def has_add_permission(self, request, obj):
        # TODO add superuser capability to add / copy an existing line / reset timeline to tweak copy job
        return False


@admin.register(TransferLog)
class TransferLogAdmin(admin.ModelAdmin):
    model = TransferLog
    list_display = ('job_id', 'tgt_host', 'table_name', 'renamed_table_schema', 'start_date', 'end_date', 'message')
    list_filter = ('job_id',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        if not request.GET.get('job_id__job_id__exact'):
            messages.warning(request, "Please Filter per request job first.")
            return TransferLog.objects.none()
        else:
            return super().get_queryset(request)

    def get_changelist(self, request, **kwargs):
        return super().get_changelist(request, **kwargs)

    def get_paginator(self, request, queryset, per_page, orphans=0, allow_empty_first_page=True):
        return super().get_paginator(request, queryset, per_page, orphans, allow_empty_first_page)


@admin.register(RequestJob)
class RequestJobAdmin(admin.ModelAdmin):
    class Media:
        js = ('dbcopy/js/dbcopy.js',)
        css = {'all': ('dbcopy/css/db_copy.css',)}

    actions = ['resubmit_jobs', ]
    # inlines = (TransferLogInline,)
    form = RequestJobForm
    list_display = ('job_id', 'src_host', 'src_incl_db', 'src_skip_db', 'tgt_host', 'username',
                    'request_date', 'end_date', 'status')  # , 'running_transfers', 'done_transfers', 'nb_transfers')
    list_per_page = 15
    search_fields = ('job_id', 'src_host', 'src_incl_db', 'src_skip_db', 'tgt_host')  # , 'username', 'request_date')
    list_filter = (DBCopyUserFilter,)
    ordering = ('-request_date', '-start_date')
    fields = ['status', 'src_host', 'tgt_host', 'email_list', 'username',
              'src_incl_db', 'src_skip_db', 'src_incl_tables', 'src_skip_tables', 'tgt_db_name', 'link_out_transfers_logs']
    # TODO re-add when available 'skip_optimize', 'wipe_target', 'convert_innodb', 'dry_run']
    readonly_fields = ('request_date', 'start_date', 'end_date', 'status', 'link_out_transfers_logs')

    def has_view_permission(self, request, obj=None):
        return request.user.is_staff

    def has_change_permission(self, request, obj=None):
        return request.user.is_staff

    def has_module_permission(self, request):
        return request.user.is_staff

    def has_add_permission(self, request):
        return request.user.is_staff

    def has_delete_permission(self, request, obj=None):
        # Allow delete only for superusers and obj owners when status avail deletion.
        return request.user.is_superuser or (
                obj is not None and self._is_deletable(obj) and request.user.username == obj.username)

    def get_fields(self, request, obj=None):
        if obj is None or obj.pk is None:
            if 'overall_status' in self.fields:
                self.fields.remove('overall_status')
            if 'link_out_transfers_logs' in self.fields:
                self.fields.remove('link_out_transfers_logs')
        return super().get_fields(request, obj)

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj, change, **kwargs)
        form.user = request.user
        return form

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        initial['email_list'] = request.user.email
        initial['username'] = request.user.username
        if 'from_request_job' in request.GET:
            obj = RequestJob.objects.get(pk=request.GET['from_request_job'])
            initial['src_host'] = obj.src_host
            initial['tgt_host'] = obj.tgt_host.split(',')
            initial['src_incl_db'] = obj.src_incl_db
            initial['src_skip_db'] = obj.src_skip_db
            initial['src_incl_tables'] = obj.src_incl_tables
            initial['src_skip_tables'] = obj.src_skip_tables
            initial['tgt_db_name'] = obj.tgt_db_name
        return initial

    def link_out_transfers_logs(self, obj):
        return mark_safe("<a href='%s'>Link</a>" % obj.get_transfer_url())

    link_out_transfers_logs.short_description = "See transfer logs"

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return super().get_readonly_fields(request, obj)
        else:
            return self.fields

    def resubmit_jobs(self, request, queryset):
        """
        Bulk resubmit jobs as they were initially.
        :return: None
        # TODO add current user email to the list if not already present.#
        """
        for query in queryset:
            new_job = RequestJob.objects.get(pk=query.pk)
            new_job.pk = None
            new_job.request_date = None
            new_job.start_date = None
            new_job.end_date = None
            new_job.username = request.user.username
            new_job.status = None
            new_job.save()
            message = 'Job {} resubmitted [new job_id {}]'.format(query.pk, new_job.pk)
            messages.add_message(request, messages.SUCCESS, message, extra_tags='', fail_silently=False)

    resubmit_jobs.short_description = 'Resubmit Jobs'

    def get_object(self, request, object_id, from_field=None):
        print('in get object')
        queryset = self.get_queryset(request)
        model = queryset.model
        try:
            obj = queryset.annotate(
                nb_transfers=Count('transfer_logs'),
                running_transfers=Count('transfer_logs',
                                        filter=Q(end_date__isnull=True))).get(**{'job_id': object_id})
            print(obj.running_transfers, obj.nb_transfers)
            return obj
        except (model.DoesNotExist, ValidationError, ValueError):
            return None

    def get_queryset(self, request):
        base_queryset = super().get_queryset(request)
        print(base_queryset.query)
        return base_queryset

    def get_paginator(self, request, queryset, per_page, orphans=0, allow_empty_first_page=True):
        return super().get_paginator(request, queryset, per_page, orphans, allow_empty_first_page)

    def change_view(self, request, object_id, form_url='', extra_context=None):
        extra_context = extra_context or {}
        if 'completion' not in self.fields:
            index = 1 if 'overall_status' in self.fields else 0
            self.fields.insert(index, 'completion')
        if 'request_date' not in self.fields:
            self.fields.append('request_date')
        if 'start_date' not in self.fields:
            self.fields.append('start_date')
        if 'end_date' not in self.fields:
            self.fields.append('end_date')
        if not request.user.is_superuser:
            extra_context['readonly'] = True
        extra_context['show_save_as_new'] = False
        extra_context['show_delete_link'] = request.user.is_superuser
        extra_context['show_save'] = False
        extra_context['show_save_and_add_another'] = False
        extra_context['show_save_and_continue'] = False
        return super().change_view(request, object_id, form_url, extra_context)

    def add_view(self, request, form_url='', extra_context=None):
        if 'completion' in self.fields:
            self.fields.remove('completion')
        return super().add_view(request, form_url, extra_context)

    def _is_deletable(self, obj):
        return obj.status not in ('Creating Requests', 'Processing Requests')

    def _get_deletable_objects(self, objs):
        if isinstance(objs, QuerySet):
            return objs.exclude(Q(status='Creating Requests') | Q(status='Processing Requests'))
        return list(filter(self._is_deletable, objs))

    def get_deleted_objects(self, objs, request):
        deletable_objs = self._get_deletable_objects(objs)
        return super().get_deleted_objects(deletable_objs, request)

    def delete_queryset(self, request, queryset):
        deletable_queryset = self._get_deletable_objects(queryset)
        deleted_count, _rows_count = deletable_queryset.delete()
        message = "Successfully deleted %(count)d %(items)s." % {
            'count': deleted_count, 'items': model_ngettext(self.opts, deleted_count)
        }
        messages.add_message(request, messages.SUCCESS, message, extra_tags='', fail_silently=False)

    def message_user(self, *args, **kwargs):
        pass

    def log_deletion(self, request, obj, obj_display):
        if self._is_deletable(obj):
            super().log_deletion(request, obj, obj_display)

    def status(self, obj):
        return format_html(
            '<div class="overall_status {}">{}</div>',
            obj.status,
            obj.status
        )

    def changelist_view(self, request, extra_context=None):
        if 'user' not in request.GET:
            # set default filter to the request user
            q = request.GET.copy()
            q['user'] = request.user
            request.GET = q
            request.META['QUERY_STRING'] = request.GET.urlencode()
        return super().changelist_view(request, extra_context)
