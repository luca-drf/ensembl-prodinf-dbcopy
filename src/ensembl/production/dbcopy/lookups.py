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
from .models import Host, Dbs2Exclude
from sqlalchemy.exc import DBAPIError

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
    paginate_by = 10

    def get_queryset(self):
        return Host.objects.qs_src_host(self.q or None, active=True)

    def get_selected_result_label(self, result):
        return '%s:%s' % (result.name, result.port)

    def get_result_value(self, result):
        return '%s:%s' % (result.name, result.port)


class TgtHostLookup(autocomplete.Select2ListView):
    model = Host
    paginate_by = 10

    def get_list(self):
        result = []
        try:
            hosts = Host.objects.qs_tgt_host_for_user(self.q or '', self.request.user)
            result = [(str(host), str(host)) for host in hosts]
            logger.debug("Results %s", result)
        except (ValueError, ObjectDoesNotExist) as e:
            # TODO manage proper error
            logger.error("Db Lookup query error: ", str(e))
            pass
        except DBAPIError as e:
            logger.error("Db Lookup query error: ", str(e.orig))
        return result


class DbLookup(autocomplete.Select2ListView):
    def get_list(self):
        """
        Return a list of all schema names
        """
        search = self.q or ''
        result = []
        if self.q:
            try:
                host, port = self.forwarded.get('db_host').split(':')
                name_filters = [search.replace('%', '.*')]
                logger.info("Filter set to %s", name_filters)
                result = get_database_set(host, port, incl_filters=name_filters,
                                          skip_filters=get_excluded_schemas())

            except (ValueError, ObjectDoesNotExist) as e:
                # TODO manage proper error
                logger.error("Db Lookup query error: ", str(e))
                pass
            except DBAPIError as e:
                logger.error("Db Lookup query error: ", str(e.orig))
        return result


class TableLookup(autocomplete.Select2ListView):
    def get_list(self):
        result = []
        included_dbs = self.forwarded.get('src_incl_db', [])
        if len(included_dbs) > 1 or any('%' in incl_db for incl_db in included_dbs):
            return ['', 'Cannot filter on table name on multiple/patterned dbs!!']
        if len(included_dbs) > 0 and self.q and len(self.q) >= 2:
            try:
                host, port = self.forwarded.get('db_host').split(':')
                database = self.forwarded.get('src_incl_db')[0]
                # TODO See if we could managed a set of default excluded tables
                logger.debug("Inspecting %s:%s/%s w/ %s", host, port, database, self.q)
                filters = ['.*' + self.q.replace('%', '.*') + '.*']
                result = get_table_set(host, port, database, incl_filters=filters)
            except (ValueError, ObjectDoesNotExist) as e:
                # TODO manage proper error
                logger.error("Db Table Lookup query error: %s ", str(e))
                pass
            except DBAPIError as e:
                logger.error("TableLookup query error: %s ", str(e.orig))
        return result

