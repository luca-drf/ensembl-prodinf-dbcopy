CHANGELOG - Ensembl Prodinf Database copy
=========================================

v1.2
----
- Fix whole server copy check issue preventing submission
- Updated Controls to remove annoying initial messages
- Updates TargetHost Lookup not to offer current typed chars 
- Added Create and Start Date time to edit view
- Corrected Style

v1.1
----
- moved RequestJob validation at model level. (Initiall in Admin form)
- Bumped django-admin-inline-paginator version to 0.2 
- Changed Django dependency requirements compatibility level
- Updated CSS to for RequestJob lists display (added colors / progress bar)
- Request Job fix user not being associated  
- Optimised queries for listing job loading time

v1.0
----
- Moved from initial production services monolithic application (https://github.com/Ensembl/ensembl-production-services)
- Django standard layout / templates integration (enable backend skinning)
- Refactored App API to enable usage of external service for db introspection
- Changed namespace to `ensembl.production.dbcopy`
- Changed app name to `ensembl_dbcopy`  
  
