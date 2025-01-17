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
import logging
from django.contrib.admin import SimpleListFilter
from django.db.models import Count, Q

logger = logging.getLogger(__name__)


class DBCopyUserFilter(SimpleListFilter):
    """
    This filter will always return a subset of the instances in a Model, either filtering by the
    user choice or by a default value.
    """
    # Human-readable title which will be displayed in the
    # right admin sidebar just above the filter options.
    title = 'User'
    # Parameter for the filter that will be used in the URL query.
    parameter_name = 'user'
    default_value = None

    def __init__(self, request, params, model, model_admin):
        super().__init__(request, params, model, model_admin)
        self.username = request.user.username

    def lookups(self, request, model_admin):
        """
        Returns a list of tuples. The first element in each
        tuple is the coded value for the option that will
        appear in the URL query. The second element is the
        human-readable name for the option that will appear
        in the right sidebar.
        """
        query = model_admin.model.objects.filter(username__isnull=False).distinct()
        list_of_users = model_admin.model.objects.filter(username__isnull=False).distinct(). \
            order_by('username').values_list('username', 'username')
        return list_of_users

    def choices(self, changelist):
        """ Enable 'All' value passed instead of empty string,
        list item to fetch all values instead of default user's ones. """
        yield {
            'selected': self.value() == "All",
            'query_string': changelist.get_query_string({self.parameter_name: 'All'}),
            'display': 'All',
        }
        for lookup, title in self.lookup_choices:
            yield {
                'selected': self.value() == str(lookup),
                'query_string': changelist.get_query_string({self.parameter_name: lookup}),
                'display': title,
            }

    def queryset(self, request, queryset):
        """
        Returns the filtered queryset based on the value
        provided in the query string and retrievable via
        `self.value()`.
        """
        # Compare the requested value to decide how to filter the queryset.
        if self.value():
            if self.value() != 'All':
                return queryset.filter(username=self.value())
            else:
                return queryset.all()
        # default query set per request user
        return queryset.filter(username=request.user)


class OverallStatusFilter(SimpleListFilter):
    title = 'Status'  # or use _('country') for translated title
    parameter_name = 'status'

    def lookups(self, request, model_admin):
        return [
            ("Complete", "Completed"),
            ("Failed", "Failed"),
            ("Running", "Running"),
            ("Submitted", "Submitted"),
        ]

    def queryset(self, request, queryset):
        if self.value() == 'Failed':
            qs = queryset.filter(end_date__isnull=False)
            qs = qs.annotate(failed_transfers=Count('transfer_logs', filter=Q(transfer_logs__size__isnull=True)))
            qs = qs.annotate(all_transfers=Count('transfer_logs'))
            return qs.filter(Q(failed_transfers__gt=0) | Q(all_transfers=0))
        elif self.value() == 'Complete':
            qs = queryset.filter(end_date__isnull=False, status="Transfer Ended")
            return qs
        elif self.value() == 'Running':
            qs = queryset.filter(start_date__isnull=False, end_date__isnull=True)
            return qs
        elif self.value() == 'Submitted':
            qs = queryset.filter(start_date__isnull=True, end_date__isnull=True)
            return qs

