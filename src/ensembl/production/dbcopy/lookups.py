# See the NOTICE file distributed with this work for additional information
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

from dal import autocomplete
from django.core.exceptions import ObjectDoesNotExist
from ensembl.production.core.db_introspects import get_database_set, get_table_set

from ensembl.production.dbcopy.models import Dbs2Exclude
from .models import Host, Group

logger = logging.getLogger(__name__)


def make_excluded_schemas():
    schemas = set()

    def closure():
        if not schemas:
            schemas.update(Dbs2Exclude.objects.values_list('table_schema', flat=True))
        return schemas
    return closure


get_excluded_schemas = make_excluded_schemas()


class SrcHostLookup(autocomplete.Select2QuerySetView):
    model = Host

    def get_queryset(self):
        qs = Host.objects.all()
        if self.q:
            qs = qs.filter(name__icontains=self.q).order_by('name')[:50]
        return qs

    def get_selected_result_label(self, result):
        return '%s:%s' % (result.name, result.port)

    def get_result_value(self, result):
        return '%s:%s' % (result.name, result.port)


class TgtHostLookup(autocomplete.Select2QuerySetView):
    model = Host

    def get_queryset(self):
        host_queryset = Host.objects.all()
        group_queryset = Group.objects.all()
        host_queryset_final = host_queryset
        # Checking that user is allowed to copy to the matching server
        # If he is not allowed, the server will be removed from the autocomplete
        if self.q:
            host_queryset = host_queryset.filter(name__icontains=self.q, active=True)
            host_queryset_final = host_queryset
            for host in host_queryset:
                group = group_queryset.filter(host_id=host.auto_id)
                if group:
                    host_groups = group.values_list('group_name', flat=True)
                    user_groups = self.request.user.groups.values_list('name', flat=True)
                    common_groups = set(host_groups).intersection(set(user_groups))
                    if not common_groups:
                        host_queryset_final = host_queryset.exclude(name=host.name)
        return host_queryset_final

    def get_selected_result_label(self, result):
        return '%s:%s' % (result.name, result.port)

    def get_result_value(self, result):
        return '%s:%s' % (result.name, result.port)


class DbLookup(autocomplete.Select2ListView):
    def get_list(self):
        """
        Return a list of all schema names
        """
        search = self.q or ''
        result = []
        if self.q:
            try:
                host = self.forwarded.get('db_host').split(':')[0]
                port = self.forwarded.get('db_host').split(':')[1]
                name_filter = search.replace('%', '.*').replace('_', '.')
                result = get_database_set(host, port, name_filter=name_filter,
                                          excluded_schemas=get_excluded_schemas())
            except (ValueError, ObjectDoesNotExist) as e:
                # TODO manage proper error
                logger.error("Db Lookup query error: ", e)
                pass
        return result


class TableLookup(autocomplete.Select2ListView):
    def get_list(self):
        result = []
        if len(self.forwarded.get('src_incl_db')) > 1:
            return ['Cannot filter on table name on multiple dbs!!']
        if self.q and len(self.q) >= 2:
            try:
                host = self.forwarded.get('db_host').split(':')[0]
                port = self.forwarded.get('db_host').split(':')[1]
                database = self.forwarded.get('src_incl_db')[0]
                # See if we could managed a set of default excluded tables
                result = get_table_set(host, port, database, self.q)
            except (ValueError, ObjectDoesNotExist) as e:
                # TODO manage proper error
                logger.error("Db Table Lookup query error: ", e)
                pass
        return result
