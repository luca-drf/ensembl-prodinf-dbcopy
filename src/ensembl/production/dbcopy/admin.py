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
from django.db.models import F, Q
from django.db.models.query import QuerySet
from django.utils.html import format_html
from django_admin_inline_paginator.admin import TabularInlinePaginated
from ensembl.production.djcore.admin import SuperUserAdmin
from ensembl.production.dbcopy.filters import DBCopyUserFilter, OverallStatusFilter

from ensembl.production.dbcopy.forms import RequestJobForm, GroupInlineForm
from ensembl.production.dbcopy.models import Host, RequestJob, Group, TargetHostGroup, TransferLog


class GroupInline(admin.TabularInline):
    model = Group
    extra = 1
    form = GroupInlineForm
    fields = ('group_name',)
    verbose_name = "Group restriction"
    verbose_name_plural = "Group restrictions"


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
    per_page = 30
    fields = ('table_schema', 'table_name', 'renamed_table_schema', 'start_date', 'end_date', 'table_status')
    readonly_fields = ('table_schema', 'table_name', 'renamed_table_schema', 'start_date', 'end_date', 'table_status')
    can_delete = False
    ordering = F('end_date').asc(nulls_first=True), F('auto_id')

    def has_add_permission(self, request, obj):
        # TODO add superuser capability to add / copy an existing line / reset timeline to tweak copy job
        return False


@admin.register(RequestJob)
class RequestJobAdmin(admin.ModelAdmin):
    class Media:
        js = ('dbcopy/js/dbcopy.js',)
        css = {'all': ('dbcopy/css/db_copy.css',)}

    actions = ['resubmit_jobs', ]
    inlines = (TransferLogInline,)
    form = RequestJobForm
    list_display = ('job_id', 'src_host', 'src_incl_db', 'src_skip_db', 'tgt_host', 'tgt_db_name', 'username',
                    'request_date', 'overall_status')
    search_fields = ('job_id', 'src_host', 'src_incl_db', 'src_skip_db', 'tgt_host', 'tgt_db_name', 'username',
                     'start_date', 'end_date', 'request_date')
    list_filter = (DBCopyUserFilter, OverallStatusFilter, 'src_host', 'tgt_host')
    ordering = ('-request_date', '-start_date')
    fields = ['overall_status', 'src_host', 'tgt_host', 'email_list', 'username',
              'src_incl_db', 'src_skip_db', 'src_incl_tables', 'src_skip_tables', 'tgt_db_name']
    # TODO re-add when available 'skip_optimize', 'wipe_target', 'convert_innodb', 'dry_run']
    readonly_fields = ('overall_status', 'request_date', 'start_date', 'end_date')

    def has_change_permission(self, request, obj=None):
        return False

    def has_module_permission(self, request):
        return request.user.is_staff

    def has_delete_permission(self, request, obj=None):
        # Allow delete only for superusers and obj owners when status avail deletion.
        return request.user.is_superuser or \
               (obj is not None and obj.overall_status in (
               'Submitted', 'Failed') and request.user.username == obj.username)

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj, change, **kwargs)
        if obj is None:
            self.fields.remove('overall_status') if 'overall_status' in self.fields else None
            pass
        form.user = request.user
        form.username = request.user.username
        form.email_list = request.user.email
        return form

    def resubmit_jobs(self, request, queryset):
        for query in queryset:
            new_job = RequestJob.objects.get(pk=query.pk)
            new_job.pk = None
            new_job.request_date = None
            new_job.start_date = None
            new_job.end_date = None
            new_job.status = None
            new_job.save()
            message = 'Job {} resubmitted [new job_id {}]'.format(query.pk, new_job.pk)
            messages.add_message(request, messages.SUCCESS, message, extra_tags='', fail_silently=False)

    resubmit_jobs.short_description = 'Resubmit Jobs'

    def change_view(self, request, object_id, form_url='', extra_context=None):
        context = extra_context or {}
        search_query = request.GET.get('search_box')
        if search_query:
            transfers_logs = self.get_object(request, object_id).transfer_logs.filter(
                Q(table_name__contains=search_query) | Q(table_schema__contains=search_query) | Q(
                    tgt_host__contains=search_query) | Q(renamed_table_schema__contains=search_query))
        else:
            transfers_logs = self.get_object(request, object_id).transfer_logs
        if transfers_logs.filter(end_date__isnull=True):
            context["running_copy"] = transfers_logs.filter(end_date__isnull=True).order_by(
                F('end_date').desc(nulls_first=True)).earliest('auto_id')
        return super().change_view(request, object_id, form_url, context)

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

    def overall_status(self, obj):
        return format_html(
            '<div class="overall_status {}">{}</div>',
            obj.overall_status,
            obj.overall_status
        )

    def get_inlines(self, request, obj):
        """Hook for specifying custom inlines."""
        if obj:
            return super().get_inlines(request, obj)
        else:
            return []

    def changelist_view(self, request, extra_context=None):
        if 'user' not in request.GET:
            # set default filter to the request user
            q = request.GET.copy()
            q['user'] = request.user
            request.GET = q
            request.META['QUERY_STRING'] = request.GET.urlencode()
        return super().changelist_view(request, extra_context)
