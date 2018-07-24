import datetime
import os
import re

from jinja2 import Template
from robot.result import Result

import Config.framework_config as framework_config
from Framework.execution.ion_results import IONResults
from Framework.execution.robot.RobotResultVisitor import RobotResultVisitor
from Framework.configuration.test_environment import TestingEnvironment
from Framework.execution.unit.ion_unit_result import UnitTestResult

TOTAL = "total"
SKIP_COUNT = "skip_count"
FAIL_COUNT = "fail_count"
ERROR_COUNT = "error_count"
PASS_COUNT = "pass_count"
RESULT_LINES = "result_lines"
DURATION = "duration"
START_TIME = "start_time"
ION_TEST_RESULT_DIR = framework_config.current_config.test_results_dir


def generate_report(test_results):
    """
    Generate each suite's detailed HTML report and summary HTML report.
    :param test_results:
    :return: None
    """

    total_tests = 0
    total_pass = 0
    total_fail = 0
    total_error = 0
    total_skip = 0

    for result in test_results:
        test_data = {}
        if isinstance(result, UnitTestResult):
            test_data = _parse_unittest(result)
        elif isinstance(result, Result):
            test_data = _parse_robot(result)
        elif isinstance(result, IONResults):
            log_loc = os.path.join(ION_TEST_RESULT_DIR, "framework.log")
            test_data = _parse_ion_result(log_loc)

    # dictionary for HTML summary report
    summary_data = []
    # TODO right now it just does pyunit test results
    for suite, info in test_data.items():
        suite_summary = {}
        headers = {}

        overall_suite_name = info[0]
        suite_cases = info[2]

        detailed_report_name = f"{suite}TestReport.html"
        summary_report_name = f"{overall_suite_name}Report.html"
        suite_result_title = f"{suite} Test Results"

        suite_stats = info[1].get('stats')
        passes = suite_stats[PASS_COUNT]
        fails = suite_stats[FAIL_COUNT]
        skips = suite_stats[SKIP_COUNT]
        errors = suite_stats[ERROR_COUNT]
        duration = suite_stats[DURATION]
        start_time = suite_stats[START_TIME]

        headers["start_time"] = start_time
        headers["duration"] = duration
        headers["status"] = f"Passes: {passes}, Fails: {fails}, Errors: {errors}, Skips: {skips}"
        # TODO dynamically fill test environment headers
        headers["system_os"] = TestingEnvironment.system_os
        headers["system_os_version"] = TestingEnvironment.system_os_version
        headers["hostname"] = TestingEnvironment.hostname
        headers["system_machine"] = TestingEnvironment.system_machine
        headers["summary_link"] = summary_report_name

        template_data = {"headers": headers,
                         "suite_cases": suite_cases,
                         "suite_result_title": suite_result_title
                         }

        curr_dir = os.path.dirname(os.path.realpath(__file__))
        template_file_path = os.sep.join([curr_dir, "SuiteReportTemplate.html"])

        render_template(template_data, template_file_path, detailed_report_name)

        # calculating totals/filling summary dictionary for summary report
        total_tests = total_tests + len(suite_cases)
        cases_list = []
        suite_result = 'pass'
        for test_case_name, test_case_steps in suite_cases.items():
            test_case_dict = {}
            test_result = test_case_steps[-1]['result']
            if test_result == 'pass':
                total_pass += 1
            elif test_result == 'fail':
                total_fail += 1
                suite_result = 'fail'
            elif test_result == 'skip':
                total_skip += 1
                suite_result = 'fail'
            else:
                total_error += 1
                suite_result = 'fail'

            # for linking between html reports
            html_link = detailed_report_name + "#" + test_case_name

            test_case_dict['test_case_name'] = test_case_name
            test_case_dict['test_result'] = test_result
            test_case_dict['html_link'] = html_link
            cases_list.append(test_case_dict)
            # empty the dict for the next set of test case info

        suite_summary['suite_name'] = suite
        suite_summary['suite_result'] = suite_result
        suite_summary['suite_test_cases'] = cases_list
        suite_summary['suite_report_html_link'] = detailed_report_name
        summary_data.append(suite_summary)

    summary_headers = {}
    suite_summary_title = f"{overall_suite_name} Report"

    # TODO dynamically fill test environment headers
    summary_headers["system_os"] = TestingEnvironment.system_os
    summary_headers["system_os_version"] = TestingEnvironment.system_os_version
    summary_headers["hostname"] = TestingEnvironment.hostname
    summary_headers["system_machine"] = TestingEnvironment.system_machine
    summary_headers["status"] = f"Passes: {total_pass}, Fails: {total_fail}," \
                                f"Errors: {total_error}, Skips: {total_skip}"
    summary_headers["total_tests"] = total_tests

    template_data = {"summary_headers": summary_headers,
                     "suite_summary_title": suite_summary_title,
                     "summary_data": summary_data
                     }

    template_file_path = os.sep.join([curr_dir, "SummaryReportTemplate.html"])
    render_template(template_data, template_file_path, summary_report_name)


def render_template(template_data: dict, template_file_path: str, template_file_name: str):
    """
    Render the template with the data provided from parsing the results log.
    :param template_data: Dictionary of headers to include into the HTML report
    :param template_file_path: Location of the HTML Template to be used
    :param template_file_name: Name of HTML file that will be created
    :return:  None
    """
    with open(template_file_path) as template_file:
        template_text = template_file.read()
        template_generator = Template(template_text)
        output = template_generator.render(template_data)

    html_report = os.path.join(ION_TEST_RESULT_DIR, template_file_name)
    with open(html_report, mode='w') as html_file:
        html_file.write(output)


def _parse_ion_result(log_file_path):
    """
    Parses an ion test log file to put into the HTML report.
    :param log_file_path: ION test log path, including file, to parse
    :return: Dictionary of suites to parse into the HTML report.
    """
    skip_count = 0
    fail_count = 0
    error_count = 0
    pass_count = 0
    suites = {}
    test_case = {}
    current_suite = ""
    previous_suite = ""
    overall_suite_name = ""
    start_time = None
    end_time = None

    with open(log_file_path) as log_file:
        test_case_steps = []
        for line in log_file:
            log_line = line
            log_breakdown = log_line.split("|")
            timestamp = log_breakdown[0].strip()
            log_type = log_breakdown[1].strip()
            log_level = log_breakdown[2].strip()
            log_message = log_breakdown[3].strip()

            if "ROBOT" in log_type:
                # TODO to add the last test suite into the dictionary, there should be a better way instead of this
                duration = str(end_time - start_time)
                test_start_time = str(start_time)

                stats = {
                    'stats': {
                        SKIP_COUNT: skip_count,
                        FAIL_COUNT: fail_count,
                        ERROR_COUNT: error_count,
                        PASS_COUNT: pass_count,
                        DURATION: duration,
                        START_TIME: test_start_time
                    }
                }
                suites[previous_suite] = [overall_suite_name, stats, test_case]
                break

            if "UnitTest" in log_type and "Starting Test Case" in log_message:
                suite_pattern = r"\(.*?\)"
                suite_pattern_result = re.search(suite_pattern, log_message)
                suite_hierarchy_list = suite_pattern_result.group(0).split(".")
                current_suite = suite_hierarchy_list[-2]

                if not overall_suite_name:
                    overall_suite_name = suite_hierarchy_list[0].replace("(", "")

                if current_suite != previous_suite:
                    if end_time is not None:
                        duration = str(end_time - start_time)
                        test_start_time = str(start_time)
                    start_time = datetime.datetime.strptime(timestamp, "%y-%m-%d %H:%M:%S")

                    if previous_suite:
                        stats = {
                            'stats': {
                                SKIP_COUNT: skip_count,
                                FAIL_COUNT: fail_count,
                                ERROR_COUNT: error_count,
                                PASS_COUNT: pass_count,
                                DURATION: duration,
                                START_TIME: test_start_time
                            }
                        }
                        suites[previous_suite] = [overall_suite_name, stats, test_case]

                    # reset counts to 0 to prepare for next iteration
                    skip_count = 0
                    fail_count = 0
                    error_count = 0
                    pass_count = 0
                    # clear test cases for next suite
                    test_case = {}

            if "TestCase" in log_type and ("STEP" in log_level or "INFO" in log_level):
                test_case_steps.append({"timestamp": timestamp, "level": log_level, "message": log_message})

            if "UnitTest" in log_type and ("ERROR" in log_level or "ASSERT" in log_level):
                test_case_steps.append({"timestamp": timestamp, "level": log_level, "message": log_message})

            if "UnitTest" in log_type and "Ending Test Case" in log_message:
                # save the suite that was run
                previous_suite = current_suite
                end_time = datetime.datetime.strptime(timestamp, "%y-%m-%d %H:%M:%S")
                log_status = log_breakdown[4].strip()
                test_case_pattern = r"\:(.*?)\("
                test_case_pattern_result = re.search(test_case_pattern, log_message)
                test_case_name = test_case_pattern_result.group(1).strip()

                last_step = test_case_steps[-1]

                if "pass" in log_status:
                    pass_count += 1
                elif "fail" in log_status:
                    fail_count += 1
                elif "incomplete" in log_status:
                    error_count += 1
                elif "skip" in log_status:
                    skip_count += 1
                last_step["result"] = log_status

                test_case[test_case_name] = test_case_steps
                # clear test steps to prepare for next test case
                test_case_steps = []

    return suites


def _parse_unittest(unittest_result):
    suite_total = unittest_result.testsRun
    skip_count = len(unittest_result.skipped)
    fail_count = len(unittest_result.failures)
    error_count = len(unittest_result.errors)
    pass_count = 0
    result_lines = []

    for test in unittest_result.tests_executed:  # type: TestCase
        # TODO if enforcing tests as an extension of the ION TestCase, this would be simpler
        #   we could set pass, fail etc when it happens

        # Check if test was skipped, get message if so
        test_name = str(test)
        msg = ""
        status = "success"

        for skip in unittest_result.skipped:
            if skip[0] == test:  # first element of tuple is the test class
                skipped = True
                status = "info"
                msg = skip[1]  # second element of tuple is message
                break
        else:
            skipped = False

        # Check if test errored, get message if so
        for err in unittest_result.errors:
            if err[0] == test:  # first element of tuple is the test class
                errored = True
                status = "warning"
                msg = err[1]  # second element of tuple is message
                break
        else:
            errored = False

        # Check if test failed, get message if so
        for fail in unittest_result.failures:
            if fail[0] == test:  # first element of tuple is the test class
                failed = True
                status = "danger"
                msg = fail[1]  # second element of tuple is message
                break
        else:
            failed = False

        if not skipped and not errored and not failed:
            pass_count += 1

        result_lines.append([test_name, status, msg, ""])

    stats = {TOTAL: suite_total,
             SKIP_COUNT: skip_count,
             FAIL_COUNT: fail_count,
             ERROR_COUNT: error_count,
             PASS_COUNT: pass_count,
             RESULT_LINES: result_lines}

    return stats


def _parse_robot(robot_result):
    result_visitor = RobotResultVisitor()
    result_visitor.visit_result(robot_result)

    result_lines = []
    suite_total = result_visitor.pass_count + result_visitor.fail_count

    for test in result_visitor.tests:
        status = test.get("test_status", "warning")
        if status == "PASS":
            status = "success"
        elif status == "FAIL":
            status = "danger"

        result_lines.append([test.get("test_name", "No Name"),
                             status,
                             test.get("test_message"), ""])

    stats = {TOTAL: suite_total,
             SKIP_COUNT: 0,
             FAIL_COUNT: result_visitor.fail_count,
             ERROR_COUNT: 0,
             PASS_COUNT: result_visitor.pass_count,
             RESULT_LINES: result_lines}

    return stats
