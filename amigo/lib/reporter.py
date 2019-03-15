#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#   amigo.py
#
#   Main class for Amigo. This class manages how reports are retrieved from GCP,
#   fetching them by projects and attributes, and saving them in disk. Finally,
#   it runs the analytics methods on fetched data.


import util
from gcp import GCPWrapper
from database import Database




class Reporter():

    def __init__(self, config):

        self.config = config
        self.database_path = util.get_value(self.config, "database_json")

        self.reports = None
        self.previous_reports = None

        self.results = None

        self.warnings = []

        self._setup()


    def _setup(self):
        """
            Set Amigo to run.
        """

        # Set output directories
        output_dir = util.get_value(self.config, "reports_dir")
        util.print_to_stdout("Setting up output directory at '{0}'".format(output_dir))
        util.create_dir(output_dir)

        # Set current report
        self.reports = util.get_full_path(util.get_value(self.config, "reports_dir"), util.get_date())
        util.create_dir(self.reports)
        util.print_to_stdout("Reports are being saved to '{0}'".format(self.reports))

        # Search for previous reports
        days_back = 30
        for day in range(1, days_back):
            self.previous_reports = util.get_full_path(util.get_value(self.config, "reports_dir"), util.get_date(day))
            if not util.is_path(self.previous_reports):
                util.print_to_stdout("No previous reports found at {0}'".format(self.previous_reports))
            else:
                util.print_to_stdout("Previous report {0} found ({1} day(s) ago)".format(self.previous_reports, day), color="yellow")
                break

        # Create Database
        self.database = Database(self.database_path)
        util.create_dir(self.database_path)
        util.print_to_stdout("Database is being saved at '{0}'".format(self.database_path))

        # Violation report config
        results_dir = util.get_value(self.config, "results_dir")
        util.create_dir(results_dir)
        results_file = util.get_value(self.config, "results_log_file")
        self.results = util.get_full_path(results_dir, results_file)
        util.print_to_stdout("Reports will be saved at '{0}'".format(self.results))


    def _record_attribute_data_to_db(self, attribute_item, attribute_data, project_name):
        """
            Save project attribute data to database.
            The data in the database is used to check against custom rules.
        """

        self.database.insert(attribute_item, attribute_data[0])
        util.print_to_stdout("Data {0} for project {1} registered in the database.".format(attribute_item, project_name))


    def _record_attribute_data_reports(self, attribute_item, attribute_data, project_name):
        """
            Save project attribute data to individual reports in disk.
            These reports are used for generating a quick diff report result.
            We use the symbol "@" to be able to split on it later, when reading
            the reports.
        """

        output_file = util.get_full_path(self.reports, project_name + "@" + attribute_item + '.json')

        util.save_to_json_file(attribute_data[0], output_file)
        util.print_to_stdout("Resource data for {0} for project {1} saved to {2}".format(attribute_item, project_name, output_file), color="yellow")


    def _fetch_projects(self):
        """
            Create a GCP instance for every existing project, saving
            the projects in the database.
        """

        gcp = GCPWrapper(self.config, "cloudresourcemanager", "v1")
        projects = gcp.fetch_attribute("projects")

        # Get any warning generated by this GCP instance.
        if gcp.warnings:
            self.warnings.extend(gcp.warnings)

        for project in projects:
            self.database.insert("projects", project)

        return len(projects)


    def _fetch_attributes_for_projects(self):
        """
            Fetch attributes for each GCP project in the database, saving the
            data in disk.
        """

        gcp_attributes = self.config["gcp_attributes"]

        for project in self.database.get_table("projects"):
            project_name = util.get_value(project, "projectId")

            # Gets all the resources specified in the config file (e.g. "compute")
            for attribute_resource, attribute_item_list in gcp_attributes.items():
                gcp = GCPWrapper(self.config, attribute_resource, "v1")

                # Loop on the attributes in of that resource (e.g. firewalls, networks, etc)
                for attribute_item in attribute_item_list:

                    attribute_data = gcp.fetch_attribute(attribute_item, project=project_name)
                    if attribute_data:
                        self._record_attribute_data_reports(attribute_item, attribute_data, project_name)
                        self._record_attribute_data_to_db(attribute_item, attribute_data, project_name)

                # Get any warning generated by this GCP instance.
                if gcp.warnings:
                    self.warnings.extend(gcp.warnings)

        return True


    def run(self):
        """
            Run Amigo.
        """

        # Fetch resources from GCP and save reports in disk.
        number_projects = self._fetch_projects()

        self._fetch_attributes_for_projects()

        util.print_to_stdout("{0} projects were retrieved.".format(number_projects), color="green")

        return self.reports, self.previous_reports
