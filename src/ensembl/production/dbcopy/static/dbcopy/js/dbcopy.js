/*jshint esversion: 6 */

(function ($) {
    "use strict";

    let SrcHostDetails;
    let TgtHostsDetails;
    let DBNames = [];
    let TableNames = [];

    $(document).ready(function () {
        $(".field-wipe_target").hide();
        $(".field-convert_innodb").hide();
        $(".field-dry_run").hide();
        let trs = $("#changelist-form tr");
        if (trs.has("td.field-overall_status div.Complete")) { trs.addClass('Complete'); }
        if (trs.has("td.field-overall_status div.Running")) { trs.addClass('Running');}
        if (trs.has("td.field-overall_status div.Incomplete")) { trs.addClass('Incomplete');}
        if (trs.has("td.field-overall_status div.Submitted")) { trs.addClass('Submitted');}
        if (trs.has("td.field-overall_status div.Scheduled")) { trs.addClass('Scheduled');}
        if (trs.has("td.field-overall_status div.Failed")) { trs.addClass('Failed');}
        let tds = $("#changelist-form tr td.field-overall_status");
        if (tds.has("div.Complete")) { tds.addClass('Complete'); }
        if (tds.has("div.Running")) { tds.addClass('Running'); }
        if (tds.has("div.Incomplete")) { tds.addClass('Incomplete'); }
        if (tds.has("div.Submitted")) { tds.addClass('Submitted'); }
        if (tds.has("div.Scheduled")) { tds.addClass('Scheduled'); }
        if (tds.has("div.Failed")) { tds.addClass('Failed'); }
        let srcHostElem = $("#id_src_host");
        let tgtHostElem = $("#id_tgt_host");

        if (srcHostElem.val() && tgtHostElem.val()) {
            SrcHostDetails = hostStringToDetails(srcHostElem.val());
            TgtHostsDetails = getHostsDetails(tgtHostElem.val());
            updateAlerts();
        }
       // $("#id_src_host").dispatchEvent(change);
        srcHostElem.on('change', function() {
            // console.log("id src _host changed triggered ", $(this).val());
            $(this).removeClass("is-invalid");
            SrcHostDetails = hostStringToDetails($(this).val());
            // console.log("src Host Details ", SrcHostDetails);
            updateAlerts();
        });
        tgtHostElem.change(function(){
            // console.log("idtgt_host changed triggered");
            $(this).removeClass("is-invalid");
            TgtHostsDetails = getHostsDetails($(this).val());
            updateAlerts();
        });
        $("#id_src_incl_db").change(function(){
            $(this).removeClass("is-invalid");
            updateAlerts();
        });
        $("#id_src_skip_db").change(function() {
            $(this).removeClass("is-invalid");
            updateAlerts();
        });
        $("#id_src_incl_tables").change(function() {
            $(this).removeClass("is-invalid");
            updateTableAlert(true);
            // // Commented until Wipe target is enabled by DBAs
            // checkWipeTarget();
        });
        $("#id_src_skip_tables").change(function(){
            $(this).removeClass("is-invalid");
            updateTableAlert(true);
        });
        $("#id_tgt_db_name").change(function () {
            $(this).removeClass("is-invalid");
            updateAlerts();
        });
        $('#requestjob_form .nav-tabs a[href="#transferlogs-tab"]').on('shown.bs.tab', function(e) {
            $('#transferlogs-tab .paginator a.page-link').each(function (index) {
                $(this).attr('href', $(this).attr('href') + "#transferlogs-tab");
            });
        });
    });


    // Commented until Wipe target feature is enabled by DBAs
    //
    function checkWipeTarget() {
        const sourceDBNames = $("#id_src_incl_db").val();
        const targetDBNames = $("#id_tgt_db_name").val();
        if (!(sourceDBNames.length || targetDBNames.length)) {
            $("#id_wipe_target").prop("disabled", "true");
        } else {
            $("#id_wipe_target").removeAttr("disabled");
        }
    }

//
// // Initialize WipeTarget
// $(function () {
//   if ($("#id_wipe_target").length) {
//     checkWipeTarget();
//   }
// });
//
// // Enable/Disable WipeTarget when target names changes
// $(function () {
//   $("#id_tgt_db_name").change(function () {
//     checkWipeTarget();
//   });
// });
//
// // Alert if wiping target
// $(function () {
//   $("#id_wipe_target").click(function () {
//     if (this.checked) {
//       if (DBNames.length) {
//         const hostsDetails = getHostsDetails("#id_tgt_host");
//         buildConflictsAlert(hostsDetails, DBNames);
//       }
//     }
//     else {
//       removeAlertAfter("#div_id_email_list");
//     }
//   });
// });

// Split a string according to a delimiter
    function split(val) {
        return val.replace(/\s*/, "").replace(/,$/, "").split(",");
    }

// Get the last item from a list
    function extractLast(term) {
        return split(term).pop();
    }

// Insert alert after
    function insertAlertAfter(elem, divID, alertText) {
        $("#table-alert").remove();
        $("#db-alert").remove();
        $($("#bootstrapAlert").html()).insertAfter(elem).attr('id', divID).append(alertText);
    }

    function insertAlertBefore(elem, divID, alertText) {
        $("#table-alert").remove();
        $("#db-alert").remove();
        $($("#bootstrapAlert").html()).insertBefore(elem).attr('id', divID).append(alertText);
    }

// Clean and split the string in elem and return an array
    function getSplitNames(elem) {
        const namesArr = split($(elem).val());
        return namesArr.filter(function (item) {
            return item !== "";
        });
    }

// Return the set difference: a1 / a2
    function arrayDiff(a1, a2) {
        return a1.filter(function (x) {
            return !a2.includes(x);
        });
    }

    function hostStringToDetails(string) {
        let details = string.split(':');
        return {'name': details[0], 'port': details[1]};
    }

    function hostDetailsToString(details) {
        return details.name + ":" + details.port;
    }

    function getHostsDetails(host) {
        // console.log('getHostsDetails', host);
        // let serverNames = getSplitNames(host);
        return $.map(host, function (val, i) {
            return hostStringToDetails(val);
        });
    }

    function insertItem(string, value) {
        // Code to allow multiple items to be selected in the autocomplete
        let terms = split(string);
        terms.pop();
        terms.push(value);
        terms.push("");
        return terms.join(",");
    }

// Fetch Databases per server
    function fetchPresentDBNames(hostsDetails, matchesDBs, thenFunc) {
        let presentDBs = [];
        let asyncCalls = [];
        $("#table-alert").remove();
        $("#db-alert").remove();

        $(hostsDetails).each(function (_i, hostDetails) {
            asyncCalls.push(
                $.post({
                    url: `/api/dbcopy/databases/${hostDetails.name}/${hostDetails.port}`,
                    dataType: "json",
                    headers: {
                        'X-CSRFToken': $('input[name="csrfmiddlewaretoken"]').attr('value'),
                    },
                    data: {
                        matches: matchesDBs
                    },
                    success: function (data) {
                        const hostString = hostDetailsToString(hostDetails);
                        data.forEach(function (dbName) {
                            presentDBs.push(hostString + "/" + dbName);
                        });
                    },
                    error: function (_request, _textStatus, _error) {
                    }
                })
            );
        });
        $.when.apply($, asyncCalls).then(function () {
            thenFunc(presentDBs);
        });
    }

// Fetch Databases per server
    function fetchPresentTableNames(hostDetails, databaseName, matchesTables, thenFunc) {
        $("#table-alert").remove();
        $("#db-alert").remove();
        $.post({
            url: `/api/dbcopy/tables/${hostDetails.name}/${hostDetails.port}/${databaseName}`,
            dataType: "json",
            headers: {
                'X-CSRFToken': $('input[name="csrfmiddlewaretoken"]').attr('value'),
            },
            data: {
                matches: matchesTables,
            },
            success: function (data) {
                thenFunc($.makeArray(data));
            },
            error: function (_request, _textStatus, _error) {
                thenFunc([]);
            }
        });
    }

    function checkDBNames(dbNames, hostDetails, thenFunc) {
        if (dbNames.length && dbNames.length > 1) {
            thenFunc(dbNames);
        } else {
            $("#db-alert").remove();
            $("#table-alert").remove();
            $.post({
                url: `/api/dbcopy/databases/${hostDetails.name}/${hostDetails.port}`,
                dataType: "json",
                headers: {
                    'X-CSRFToken': $('input[name="csrfmiddlewaretoken"]').attr('value'),
                },
                data: {
                    search: dbNames[0],
                },
                success: function (data) {
                    thenFunc($.makeArray(data));
                },
                error: function (_request, _textStatus, _error) {
                    thenFunc([]);
                }
            });
        }
    }

    function checkTableNames(tableNames, hostDetails, databaseName, thenFunc) {
        if (tableNames.length) {
            thenFunc(tableNames);
        } else {
            $("#table-alert").remove();
            $("#db-alert").remove();
            $.post({
                url: `/api/dbcopy/tables/${hostDetails.name}/${hostDetails.port}/${databaseName}`,
                headers: {
                    'X-CSRFToken': $('input[name="csrfmiddlewaretoken"]').attr('value'),
                },
                dataType: "json",
                success: function (data) {
                    thenFunc($.makeArray(data));
                },
                error: function (_request, _textStatus, _error) {
                    thenFunc([]);
                }
            });
        }
    }

    function updateAlerts() {
        // console.log('tgtDBNames', $("#id_tgt_db_name").val());
        const tgtDBNames = getSplitNames("#id_tgt_db_name");
        //console.log('tgtDBNames', tgtDBNames, $("#id_tgt_db_name").val());
        //console.log('inclDBNames', $("#id_src_incl_db").val());
        // Now is already an array
        const inclDBNames = $("#id_src_incl_db").val();
        //console.log('inclDBNames', inclDBNames);
        //console.log('skipDBNames', $("#id_src_skip_db").val());
        const skipDBNames = $("#id_src_skip_db").val();
        //console.log('skipDBNames', skipDBNames, $("#id_src_skip_db").val());

        if (SrcHostDetails && SrcHostDetails.name) {
            if (tgtDBNames.length) {
                DBNames = tgtDBNames;
                updateTableAlert();
            } else if (!skipDBNames.length) {
                checkDBNames(inclDBNames, SrcHostDetails, function (foundDBNames) {
                    DBNames = foundDBNames;
                    updateTableAlert();
                });
            } else {
                checkDBNames(inclDBNames, SrcHostDetails, function (foundInclDBNames) {
                    checkDBNames(skipDBNames, SrcHostDetails, function (foundSkipDBNames) {
                        DBNames = arrayDiff(foundInclDBNames, foundSkipDBNames);
                        updateTableAlert();
                    });
                });
            }
        } else {
            rebuildAlerts();
        }
    }

    function updateTableAlert(tableOnly) {
        if (DBNames.length === 1) {
            const inclTables = $("#id_src_incl_tables").val();
            const skipTables = $("#id_src_skip_tables").val();

            checkTableNames(inclTables, SrcHostDetails, DBNames[0], function (foundTableNames) {
                TableNames = arrayDiff(foundTableNames, skipTables);
                rebuildAlerts(tableOnly);
            });
        } else {
            TableNames = [];
            rebuildAlerts(tableOnly);
        }
    }

    function buildAlertText(alertMsg, lines) {
        let alertText = "";
        if (lines.length > 0) {
            alertText += alertMsg;
            alertText += "<ul>";
            lines.forEach(function (value) {
                alertText += "<li>" + value + "</li>";
            });
            alertText += "</ul>";
        }
        return alertText;
    }

    function buildDBConflictsAlert(hostsDetails, dbNames) {
        fetchPresentDBNames(hostsDetails, dbNames, function (toWipeDBs) {
            let alertMsg = "<strong>Alert!</strong> The following database(s) are already present:";
            const alertText = buildAlertText(alertMsg, toWipeDBs);
            if (alertText.length) {
                insertAlertAfter($(".field-src_skip_db"), "db-alert", alertText);
            }
        });
    }

    function buildTableConflictsAlert(hostDetails, databaseName, tableNames) {
        fetchPresentTableNames(hostDetails, databaseName, tableNames, function (foundTableNames) {
            let alertMsg = "<strong>Alert!</strong> The following table(s) are already present in the selected database:";
            const alertText = buildAlertText(alertMsg, foundTableNames);
            if (alertText.length) {
                insertAlertAfter($(".field-src_skip_tables"), "table-alert", alertText);
            }
        });
    }

    function rebuildAlerts(tableOnly) {
        if (SrcHostDetails && SrcHostDetails.name && TgtHostsDetails && TgtHostsDetails.length && DBNames.length) {
            $("#submit-id-submit").prop("disabled", "true");
            $("#table-alert").remove();
            if (TableNames.length && TgtHostsDetails.length === 1) {
                buildTableConflictsAlert(TgtHostsDetails[0], DBNames[0], TableNames);
            }
            if (!tableOnly) {
                $("#db-alert").remove();
                buildDBConflictsAlert(TgtHostsDetails, DBNames);
            }
            $("#submit-id-submit").removeAttr("disabled");
        } else {
            $("#db-alert").remove();
            $("#table-alert").remove();
        }
    }

//set host target
    function targetHosts() {
        let selectVal = $("#id_tgt_group_host option:selected").val();
        if (selectVal !== '') {
            $('#id_tgt_host').val(selectVal);
        }
    }


})(jQuery || django.jQuery);
