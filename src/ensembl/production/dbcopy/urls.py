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
from django.urls import path

from .views import reset_failed_jobs, requestjob_checks_warning, group_choice
from .lookups import SrcHostLookup, TgtHostLookup, DbLookup, TableLookup
from django.contrib.admin.views.decorators import staff_member_required

app_name = 'ensembl_dbcopy'

urlpatterns = [
    path('reset_failed_jobs/<uuid:job_id>', reset_failed_jobs, name='reset_failed_jobs'),
    path('grouphoice', group_choice, name='group_choice'),
    path('lookups/srchost', staff_member_required(SrcHostLookup.as_view()), name='src-host-autocomplete'),
    path('lookups/tgthost', staff_member_required(TgtHostLookup.as_view()), name='tgt-host-autocomplete'),
    path('lookups/srcdb', staff_member_required(DbLookup.as_view()), name='host-db-autocomplete'),
    path('lookups/srctables', staff_member_required(TableLookup.as_view()), name='host-db-table-autocomplete'),
    path('jobschecks/dbnames/', requestjob_checks_warning, name='job-checks-host'),
]
