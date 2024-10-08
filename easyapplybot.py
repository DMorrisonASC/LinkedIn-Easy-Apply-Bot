from __future__ import annotations

import json
import csv
import logging
import traceback
import os
import random
import re
import time
from datetime import datetime, timedelta
import getpass
from pathlib import Path

import pandas as pd
import pyautogui
import yaml
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.support.ui import Select
from selenium.common.exceptions import TimeoutException
from selenium.common.exceptions import StaleElementReferenceException
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from selenium.webdriver.chrome.service import Service as ChromeService
import webdriver_manager.chrome as ChromeDriverManager
ChromeDriverManager = ChromeDriverManager.ChromeDriverManager


log = logging.getLogger(__name__)


def setupLogger() -> None:
    dt: str = datetime.strftime(datetime.now(), "%m_%d_%y %H_%M_%S ")

    if not os.path.isdir('./logs'):
        os.mkdir('./logs')

    # TODO need to check if there is a log dir available or not
    logging.basicConfig(filename=('./logs/' + str(dt) + 'applyJobs.log'), filemode='w',
                        format='%(asctime)s::%(name)s::%(levelname)s::%(message)s', datefmt='./logs/%d-%b-%y %H:%M:%S')
    log.setLevel(logging.DEBUG)
    c_handler = logging.StreamHandler()
    c_handler.setLevel(logging.DEBUG)
    c_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', '%H:%M:%S')
    c_handler.setFormatter(c_format)
    log.addHandler(c_handler)


class EasyApplyBot:
    setupLogger()
    # MAX_SEARCH_TIME is 10 hours by default, feel free to modify it
    MAX_SEARCH_TIME = 60 * 60

    def __init__(self,
                 username,
                 password,
                 phone_number,
                 # profile_path,
                 salary,
                 rate,
                 uploads={},
                 filename='output.csv',
                 blacklist=[],
                 blackListTitles=[],
                 experience_level=[]
                 ) -> None:

        log.info("Welcome to Easy Apply Bot")
        dirpath: str = os.getcwd()
        log.info("current directory is : " + dirpath)
        log.info("Please wait while we prepare the bot for you")
        if experience_level:
            experience_levels = {
                1: "Entry level",
                2: "Associate",
                3: "Mid-Senior level",
                4: "Director",
                5: "Executive",
                6: "Internship"
            }
            applied_levels = [experience_levels[level] for level in experience_level]
            log.info("Applying for experience level roles: " + ", ".join(applied_levels))
        else:
            log.info("Applying for all experience levels")
        

        self.uploads = uploads
        self.salary = salary
        self.rate = rate
        # self.profile_path = profile_path
        past_ids: list | None = self.get_appliedIDs(filename)
        self.appliedJobIDs: list = past_ids if past_ids != None else []
        self.filename: str = filename
        self.options = self.browser_options()
        self.browser = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=self.options)
        self.wait = WebDriverWait(self.browser, 30)
        self.blacklist = blacklist
        self.blackListTitles = blackListTitles
        self.start_linkedin(username, password)
        self.phone_number = phone_number
        self.experience_level = experience_level


        self.locator = {
            "human_verification" : (By.XPATH, "//h1[text()=\"Let’s do a quick security check\"]"),
            "continue_applying": (By.XPATH, "//button[.//span[contains(text(), 'Continue applying')]]"),
            "next": (By.CSS_SELECTOR, "button[aria-label='Continue to next step']"),
            "review": (By.CSS_SELECTOR, "button[aria-label='Review your application']"),
            "submit": (By.CSS_SELECTOR, "button[aria-label='Submit application']"),
            "error": (By.CLASS_NAME, "artdeco-inline-feedback__message"),
            "upload_resume": (By.XPATH, "//*[contains(@id, 'jobs-document-upload-file-input-upload-resume')]"),
            "upload_cv": (By.XPATH, "//*[contains(@id, 'jobs-document-upload-file-input-upload-cover-letter')]"),
            "follow": (By.CSS_SELECTOR, "label[for='follow-company-checkbox']"),
            "upload": (By.NAME, "file"),
            "search": (By.CLASS_NAME, "jobs-search-results-list"),
            "links": (By.XPATH, '//div[@data-job-id]'),  # Corrected this line
            "fields": (By.CLASS_NAME, "jobs-easy-apply-form-section__grouping"),
            "radio_select": (By.XPATH, ".//input[starts-with(normalize-space(@id), 'urn:li:fsd_formElement:urn:li:jobs_applyformcommon_easyApplyFormElement:') and @type='radio' and @value='Yes']"),
            "multi_select": (By.XPATH, ".//select[starts-with(normalize-space(@id), 'text-entity-list-form-component-formElement-urn-li-jobs-applyformcommon-easyApplyFormElement-') and @required='']"),
            "text_select": (By.XPATH, ".//input[starts-with(@id, 'single-line-text-form-component-formElement-urn-li-jobs-applyformcommon-easyApplyFormElement-') and @type='text']"),
            "input_select": (By.CSS_SELECTOR, 'input[type="radio"], input[type="checkbox"]'),
            "text_area": (By.TAG_NAME, "textarea"),
            "2fa_oneClick": (By.ID, 'reset-password-submit-button'),
            "easy_apply_button": (By.XPATH, '//button[contains(@class, "jobs-apply-button")]'),
            "date_posted_button": (By.XPATH, '//button[contains(@id, "searchFilter_timePostedRange")]'),
            "date_posted_expanded": (By.XPATH, '//button[contains(@id, "searchFilter_timePostedRange")]'),

        }


        #initialize questions and answers file
        self.qa_file = Path("qa.csv")
        self.answers = {}

        #if qa file does not exist, create it
        if self.qa_file.is_file():
            df = pd.read_csv(self.qa_file)
            for index, row in df.iterrows():
                self.answers[row['Question']] = row['Answer']
        #if qa file does exist, load it
        else:
            df = pd.DataFrame(columns=["Question", "Answer"])
            df.to_csv(self.qa_file, index=False, encoding='utf-8')


    def get_appliedIDs(self, filename) -> list | None:
        try:
            df = pd.read_csv(filename,
                             header=None,
                             names=['timestamp', 'jobID', 'job', 'company', 'attempted', 'result'],
                             lineterminator='\n',
                             encoding='utf-8')

            df['timestamp'] = pd.to_datetime(df['timestamp'], format="%Y-%m-%d %H:%M:%S")
            df = df[df['timestamp'] > (datetime.now() - timedelta(days=2))]
            jobIDs: list = list(df.jobID)
            log.info(f"{len(jobIDs)} jobIDs found")
            return jobIDs
        except Exception as e:
            log.info(str(e) + "   jobIDs could not be loaded from CSV {}".format(filename))
            return None

    def browser_options(self):
        options = webdriver.ChromeOptions()
        options.add_argument("--start-maximized")
        options.add_argument("--ignore-certificate-errors")
        options.add_argument('--no-sandbox')
        options.add_argument("--disable-extensions")
        #options.add_argument(r'--remote-debugging-port=9222')
        #options.add_argument(r'--profile-directory=Person 1')

        # Disable webdriver flags or you will be easily detectable
        options.add_argument("--disable-blink-features")
        options.add_argument("--disable-blink-features=AutomationControlled")

        # Load user profile
        #options.add_argument(r"--user-data-dir={}".format(self.profile_path))
        return options

    def start_linkedin(self, username, password) -> None:
        log.info("Logging in.....Please wait :)")
        self.browser.get("https://www.linkedin.com/login?trk=guest_homepage-basic_nav-header-signin")

        time.sleep(10)

        try:
            user_field = self.browser.find_element("id", "username")
            pw_field = self.browser.find_element("id", "password")
            
            # Wait for the login button to be present before interacting with it
            WebDriverWait(self.browser, 10).until(
                EC.presence_of_element_located((By.XPATH, "//button[normalize-space(text())='Sign in']"))
            )

            login_button = self.browser.find_element("xpath", "//button[normalize-space(text())='Sign in']"
)
            
            user_field.send_keys(username)
            time.sleep(0.5)
            user_field.send_keys(Keys.TAB)
            time.sleep(5)
            pw_field.send_keys(password)
            time.sleep(5)
            
            # Click the login button after ensuring it is clickable
            login_button.click()
            time.sleep(20)

        except TimeoutException:
            log.info("TimeoutException! Username/password field or login button not found")
        except NoSuchElementException as e:
            log.error(f"Element not found: {e}")

    def fill_data(self) -> None:
        self.browser.set_window_size(1, 1)
        self.browser.set_window_position(2000, 2000)

    def start_apply(self, positions, locations) -> None:
        start: float = time.time()
        self.fill_data()
        self.positions = positions
        self.locations = locations
        combos: list = []
        while len(combos) < len(positions) * len(locations):
            position = positions[random.randint(0, len(positions) - 1)]
            location = locations[random.randint(0, len(locations) - 1)]
            combo: tuple = (position, location)
            if combo not in combos:
                combos.append(combo)
                log.info(f"Applying to {position}: {location}")
                location = "&location=" + location
                self.applications_loop(position, location)
            if len(combos) > 500:
                break

    # self.finish_apply() --> this does seem to cause more harm than good, since it closes the browser which we usually don't want, other conditions will stop the loop and just break out

    def applications_loop(self, position, location):

        count_application = 0
        count_job = 0
        jobs_per_page = 0
        start_time: float = time.time()

        log.info("Looking for jobs.. Please wait..")

        self.browser.set_window_position(1, 1)
        self.browser.maximize_window()
        self.browser, _ = self.next_jobs_page(position, location, jobs_per_page, experience_level=self.experience_level)
        log.info("Set and maximize window")

        while time.time() - start_time < self.MAX_SEARCH_TIME:
            # time.sleep(8)
            try:
                log.info(f"{(self.MAX_SEARCH_TIME - (time.time() - start_time)) // 60} minutes left in this search")

                # # Check for human verification
                # if self.is_present(self.locator["human_verification"]):  # Make sure to define this locator
                #     log.warning("Human verification detected. Please complete the verification.")
                #     while self.is_present(self.locator["human_verification"]):
                #         time.sleep(10)  # Pause and wait until the user completes verification

                randoTime: float = random.uniform(1.5, 2.9)
                log.debug(f"Sleeping for {round(randoTime, 1)}")
                self.load_page(sleep=0.5)

                if self.is_present(self.locator["search"]):
                    
                    scrollresults = self.get_elements("search")

                    for i in range(300, 5000, 100):
                        self.browser.execute_script("arguments[0].scrollTo(0, {})".format(i), scrollresults[0])
                        time.sleep(0.5)  # Wait for new elements to load

                if self.is_present(self.locator["links"]):
                    links = self.get_elements("links")
                    
                    jobIDs = {}

                    for link in links:

                        try:
                            # Look for the "Applied" status within the footer section of the job card
                            applied_status = link.find_element(By.XPATH, ".//div/ul/li[contains(@class, 'job-card-container__footer-job-state') and normalize-space(.)='Applied']")

                            if applied_status.is_displayed():
                                log.debug("Job already applied: {}".format(link.text))
                                continue  # Skip this job card if it's already applied

                        except NoSuchElementException:
                            if link.text not in self.blacklist:
                                jobID = link.get_attribute("data-job-id")
                                if jobID == "search":
                                    log.debug("Job ID not found, search keyword found instead? {}".format(link.text))
                                    continue
                                else:
                                    # If "Applied" status somehow passes, check if `JobID` is already in dict
                                    # Ensure that don't get 
                                    if jobID not in jobIDs:
                                        jobIDs[jobID] = "To be processed"
                    
                    if len(jobIDs) > 0:
                        self.apply_loop(jobIDs)

                    self.browser, jobs_per_page = self.next_jobs_page(position, location, jobs_per_page, experience_level=self.experience_level)

                else:
                    self.browser, jobs_per_page = self.next_jobs_page(position, location, jobs_per_page, experience_level=self.experience_level)

            except Exception as e:
                print(e)
             
    def apply_loop(self, jobIDs):
        for jobID in jobIDs:
            if jobIDs[jobID] == "To be processed":
                applied = self.apply_to_job(jobID)
                if applied:
                    log.info(f"Applied to {jobID}")
                else:
                    log.info(f"Failed to apply to {jobID}")
                del jobIDs[jobID]

    def apply_to_job(self, jobID):
        # #self.avoid_lock() # annoying

        # get job page
        self.get_job_page(jobID)

        # let page load
        time.sleep(1)

        # get easy apply button
        button = self.get_easy_apply_button()
    
        # word filter to skip positions not wanted
        if button is not False:
            if any(word in self.browser.title for word in blackListTitles):
                log.info('skipping this application, a blacklisted keyword was found in the job position')
                string_easy = "* Contains blacklisted keyword"
                result = False
            else:
                string_easy = "* has Easy Apply Button"
                log.info("Clicking the EASY apply button")
                button.click()

                clicked = True
                time.sleep(1)
                self.fill_out_fields()
                result: bool = self.send_resume()
                if result:
                    string_easy = "*Applied: Sent Resume"
                else:
                    string_easy = "*Did not apply: Failed to send Resume"

        elif "You applied on" in self.browser.page_source:
            log.info("You have already applied to this position.")
            string_easy = "* Already Applied"
            result = False
        else:
            log.info("The Easy apply button does not exist.")
            string_easy = "* Doesn't have Easy Apply Button"
            result = False


        # position_number: str = str(count_job + jobs_per_page)
        log.info(f"\nPosition {jobID}:\n {self.browser.title} \n {string_easy} \n")

        self.write_to_file(button, jobID, self.browser.title, result)
        return result

    def write_to_file(self, button, jobID, browserTitle, result) -> None:
        def re_extract(text, pattern):
            target = re.search(pattern, text)
            if target:
                target = target.group(1)
            return target

        timestamp: str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        attempted: bool = False if button == False else True
        job = re_extract(browserTitle.split(' | ')[0], r"\(?\d?\)?\s?(\w.*)")
        company = re_extract(browserTitle.split(' | ')[1], r"(\w.*)")

        toWrite: list = [timestamp, jobID, job, company, attempted, result]
        with open(self.filename, 'a+') as f:
            writer = csv.writer(f)
            writer.writerow(toWrite)

    def get_job_page(self, jobID):

        job: str = 'https://www.linkedin.com/jobs/view/' + str(jobID)
        self.browser.get(job)
        self.job_page = self.load_page(sleep=0.5)
        return self.job_page

    def get_easy_apply_button(self):
        EasyApplyButton = False
        try:
            buttons = self.get_elements("easy_apply_button")

            for button in buttons:
                if "Easy Apply" in button.text or "Continue applying" in button.text:
                    EasyApplyButton = button
                    self.wait.until(EC.element_to_be_clickable(EasyApplyButton))
                else:
                    log.debug("Easy Apply button not found")
            
        except Exception as e: 
            print("Exception:",e)
            log.debug("Easy Apply button not found")

        return EasyApplyButton
        
    def get_continue_button(self):
        continueButton = False
        try:
            buttons = self.get_elements("easy_apply_button")

            for button in buttons:
                if "Easy Apply" in button.text or "Continue applying" in button.text:
                    EasyApplyButton = button
                    self.wait.until(EC.element_to_be_clickable(continueButton))
                else:
                    log.debug("Easy Apply button not found")
            
        except Exception as e: 
            print("Exception:",e)
            log.debug("Easy Apply button not found")

        return EasyApplyButton

    def fill_out_fields(self):

        fields = self.browser.find_elements(By.CLASS_NAME, "jobs-easy-apply-form-section__grouping")
        for field in fields:

            if "Mobile phone number" in field.text:
                field_input = field.find_element(By.TAG_NAME, "input")
                field_input.clear()
                field_input.send_keys(self.phone_number)
        return


    def get_elements(self, type) -> list:
        elements = []
        element = self.locator[type]
        if self.is_present(element):
            elements = self.browser.find_elements(element[0], element[1])
        return elements

    def is_present(self, locator):
        return len(self.browser.find_elements(locator[0],
                                              locator[1])) > 0

    def is_found_field(self, locator, field):
        try:
            return len(field.find_elements(locator[0], locator[1])) > 0
        except Exception as e:
            print(f"Error occurred while finding elements: {e}")
            return False

    def get_child_elements(self, locator, field):
        try:
            return field.find_elements(locator[0], locator[1])
        except Exception as e:
            print(f"Error occurred while finding elements: {e}")
            return []  # Return an empty list instead of False



    def send_resume(self) -> bool:
        def is_present(button_locator) -> bool:
            return len(self.browser.find_elements(button_locator[0],
                                                  button_locator[1])) > 0

        try:
            #time.sleep(random.uniform(1.5, 2.5))
            next_locator = (By.CSS_SELECTOR,
                            "button[aria-label='Continue to next step']")
            review_locator = (By.CSS_SELECTOR,
                              "button[aria-label='Review your application']")
            submit_locator = (By.CSS_SELECTOR,
                              "button[aria-label='Submit application']")
            error_locator = (By.CLASS_NAME,"artdeco-inline-feedback__message")
            upload_resume_locator = (By.XPATH, '//span[text()="Upload resume"]')
            upload_cv_locator = (By.XPATH, '//span[text()="Upload cover letter"]')
            # WebElement upload_locator = self.browser.find_element(By.NAME, "file")
            follow_locator = (By.CSS_SELECTOR, "label[for='follow-company-checkbox']")

            submitted = False
            loop = 0

            while loop < 2:
                print("Entered")
                time.sleep(2)
                # Upload resume
                if is_present(upload_resume_locator):
                    #upload_locator = self.browser.find_element(By.NAME, "file")
                    try:
                        resume_locator = self.browser.find_element(By.XPATH, "//*[contains(@id, 'jobs-document-upload-file-input-upload-resume')]")
                        resume = self.uploads["Resume"]
                        resume_locator.send_keys(resume)
                    except Exception as e:
                        log.error(e)
                        log.error("Resume upload failed")
                        log.debug("Resume: " + resume)
                        log.debug("Resume Locator: " + str(resume_locator))
                # Upload cover letter if possible
                if is_present(upload_cv_locator):
                    cv = self.uploads["Cover Letter"]
                    cv_locator = self.browser.find_element(By.XPATH, "//*[contains(@id, 'jobs-document-upload-file-input-upload-cover-letter')]")
                    cv_locator.send_keys(cv)

                    #time.sleep(random.uniform(4.5, 6.5))
                if len(self.get_elements("follow")) > 0:
                    elements = self.get_elements("follow")
                    for element in elements:
                        button = self.wait.until(EC.element_to_be_clickable(element))
                        button.click()

                if len(self.get_elements("submit")) > 0:
                    elements = self.get_elements("submit")
                    for element in elements:
                        button = self.wait.until(EC.element_to_be_clickable(element))
                        button.click()
                        log.info("Application Submitted")
                        submitted = True
                        break

                elif len(self.get_elements("error")) > 0:

                    print("Length", len(self.get_elements("error")))
                    
                    if "application was sent" in self.browser.page_source:
                        log.info("Application Submitted")
                        submitted = True
                        break

                    else:
                        while True:
                            log.info("Please answer the questions, waiting 5 seconds...")
                            time.sleep(5)

                            self.process_questions()

                            if "application was sent" in self.browser.page_source:
                                log.info("Application Submitted")
                                submitted = True
                                break
                            elif is_present(self.locator["easy_apply_button"]):
                                submitted = False
                                break

                elif len(self.get_elements("next")) > 0:
                    elements = self.get_elements("next")
                    for element in elements:
                        button = self.wait.until(EC.element_to_be_clickable(element))
                        button.click()

                elif len(self.get_elements("continue_applying")) > 0:
                    elements = self.get_elements("continue_applying")
                    for element in elements:
                        button = self.wait.until(EC.element_to_be_clickable(element))
                        button.click()

                elif len(self.get_elements("review")) > 0:
                    elements = self.get_elements("review")
                    for element in elements:
                        button = self.wait.until(EC.element_to_be_clickable(element))
                        button.click()

                # elif len(self.get_elements("follow")) > 0:
                #     elements = self.get_elements("follow")
                #     for element in elements:
                #         button = self.wait.until(EC.element_to_be_clickable(element))
                #         button.click()
                # loop += 1

        except Exception as e:
            log.error(e)
            log.error("cannot apply to this job")
            pass

        return submitted

    def process_questions(self):
        time.sleep(3)

        form = self.get_elements("fields")  # Getting form elements

        print("Length: ", len(form))

        for i in range(len(form)):  

            try:
                # Attempt to re-locate the elements dynamically inside the loop
                form = self.get_elements("fields")
                field = form[i]
                question = field.text.strip()  # Ensure question text is stripped of whitespace
                
                # Get answer for each question individually
                answer = self.ans_question(question.lower())  

            except StaleElementReferenceException:
                log.warning(f"Element became stale: {field}, re-fetching form elements.")
                continue

            # Clear existing selections
            try:
                # Unselect radio buttons
                if self.is_found_field(self.locator["radio_select"], field):
                    # Returns a list of web elements
                    radio_buttons = self.get_child_elements(self.locator["radio_select"], field)

                    for radio_button in radio_buttons: # `radio_button` is a web element
                        self.browser.execute_script("""
                            arguments[0].checked = false;
                            arguments[0].dispatchEvent(new Event('change'));
                        """, radio_button)
                        log.info("Radio button unselected")

                # Unselect multi-select options
                elif self.is_found_field(self.locator["multi_select"], field):
                    # Get the first and only select element
                    select_element = self.get_child_elements(self.locator["multi_select"], field)[0]  # `select_element` is a web element

                    # Reset to the default value
                    self.browser.execute_script("arguments[0].selectedIndex = 0; arguments[0].dispatchEvent(new Event('change'));", select_element)
                    log.info("Multi-select reset to default value: 'Select an option'")


            except Exception as e:
                log.error(f"Error clearing existing selections: {e}")

        time.sleep(1)

        for i in range(len(form)):
            try:
                # Attempt to re-locate the elements dynamically inside the loop
                form = self.get_elements("fields")
                field = form[i]
                question = field.text.strip()  # Strip whitespace from question
                
                log.info(f"Processing question: {question}")
                answer = self.ans_question(question.lower())  # Get answer based on the current question
                log.info(f"Answer determined: {answer}")

            except StaleElementReferenceException:
                log.warning(f"Element became stale: {field}, re-fetching form elements.")
                continue

            # Scroll the field into view before interacting
            self.browser.execute_script("arguments[0].scrollIntoView(true);", field)

            # Check if input type is radio button
            if self.is_found_field(self.locator["radio_select"], field) and answer.lower() in ["yes", "no", "1", "0"]:
                try:
                    radio_buttons = self.get_child_elements(self.locator["radio_select"], field)

                    if radio_buttons is None or len(radio_buttons) == 0:
                        log.error(f"No radio buttons found for question: {question}")
                        continue

                    selected = False

                    for radio_button in radio_buttons:
                        if radio_button.get_attribute('value').lower() == answer.lower():
                            WebDriverWait(field, 10).until(EC.element_to_be_clickable(radio_button))
                            self.browser.execute_script("""
                                arguments[0].click();
                                arguments[0].dispatchEvent(new Event('change'));
                            """, radio_button)
                            log.info(f"Radio button selected: {radio_button.get_attribute('value')}")
                            selected = True

                    if not selected:
                        log.info("Exact match not found, looking for closest answer...")
                        closest_match = None
                        for radio_button in radio_buttons:
                            radio_value = radio_button.get_attribute('value').lower()
                            if "yes" in radio_value or "no" in radio_value:
                                closest_match = radio_button

                        if closest_match:
                            WebDriverWait(field, 10).until(EC.element_to_be_clickable(closest_match))
                            self.browser.execute_script("""
                                arguments[0].click();
                                arguments[0].dispatchEvent(new Event('change'));
                            """, closest_match)
                            log.info(f"Closest radio button selected: {closest_match.get_attribute('value')}")
                            
                        else:
                            log.warning("No suitable radio button found to select. Picking first option")
                            firstOption = radio_buttons[0]
                            WebDriverWait(field, 10).until(EC.element_to_be_clickable(firstOption))
                            self.browser.execute_script("""
                                arguments[0].click();
                                arguments[0].dispatchEvent(new Event('change'));
                            """, firstOption)
                            
                except StaleElementReferenceException:
                    log.warning(f"Retrying due to stale element.")

                except Exception as e:
                    log.error(f"Radio button error for question: {question}, answer: {answer}")
                    log.error(traceback.format_exc())  # Full traceback for better debugging
                
            # Multi-select case
            elif self.is_found_field(self.locator["multi_select"], field):
                max_retries = 5
                retry_count = 0
                while retry_count < max_retries:
                    try:
                        select_element = WebDriverWait(field, 10).until(
                            EC.presence_of_element_located(self.locator["multi_select"])
                        )

                        foundChoice = False

                        options = select_element.find_elements(By.TAG_NAME, "option")
                        for option in options:
                            if answer.lower() in option.text.strip().lower():
                                option.click()
                                foundChoice = True
                                log.info(f"Option selected: {option.text}")
                                break

                        if foundChoice == False:
                            options[1].click()
                            log.info(f"1st Option selected: {options[1].text}")

                        break  # Exit the loop if successful
                    except StaleElementReferenceException:
                        retry_count += 1
                        log.warning(f"Retrying due to stale element. Attempt {retry_count}/{max_retries}")
                    
                    except Exception as e:
                        retry_count += 1
                        log.error(f"Multi-select error: {e}")
                        break

            # Handle text input fields
            elif self.is_found_field(self.locator["text_select"], field):
                try:
                    
                    text_field = WebDriverWait(field, 10).until(
                            EC.presence_of_element_located(self.locator["text_select"])
                        )
                    time.sleep(3)
                    text_field.clear()
                    time.sleep(0.5)
                    text_field.send_keys(answer)
                    log.info(f"Text input field populated with: {answer}")
                except Exception as e:
                    log.error(f"(process_questions(1)) Text field error: {e}") 
            # Hanlde textarea fields
            elif self.is_found_field(self.locator["text_area"], field):
                try:
                    text_area = WebDriverWait(field, 10).until(
                            EC.presence_of_element_located(self.locator["text_area"])
                        )
                    time.sleep(3)
                    text_area.clear()
                    time.sleep(0.5)
                    text_area.send_keys(answer)
                    log.info(f"Text input field populated with: {answer}")
                except Exception as e:
                    log.error(f"(process_questions(1)) Text field error: {e}")

            # Handle fieldset fields
            elif self.is_found_field(self.locator["input_select"], field):  # Adjust options as needed
                try:
                    select_elements = self.get_child_elements(self.locator["input_select"], field)

                    if select_elements is None or len(select_elements) == 0:
                        log.error(f"No select elements found for question: {question}")
                        continue

                    selected = False

                    for select_element in select_elements:
                        if answer.lower() in select_element.get_attribute('data-test-text-selectable-option__input').lower():
                            WebDriverWait(field, 10).until(EC.element_to_be_clickable(select_element))
                            self.browser.execute_script("""arguments[0].selected = true;""", select_element)
                            log.info(f"Select element chosen: {select_element.get_attribute('value')}")
                            selected = True
                            break  # Exit loop once the option is selected

                    if not selected:
                        log.info("Exact match not found, looking for closest answer...")
                        closest_match = None
                        for select_element in select_elements:
                            select_value = select_element.get_attribute('value').lower()
                            if "option1" in select_value or "option2" in select_value or "option3" in select_value:  # Adjust as needed
                                closest_match = select_element
                                break

                        if closest_match:
                            WebDriverWait(field, 10).until(EC.element_to_be_clickable(closest_match))
                            self.browser.execute_script("""arguments[0].selected = true;""", closest_match)
                            log.info(f"Closest select element chosen: {closest_match.get_attribute('value')}")
                        else:
                            log.warning("No suitable select option found. Picking 2nd option")
                            firstOption = select_elements[1]
                            WebDriverWait(field, 10).until(EC.element_to_be_clickable(firstOption))
                            self.browser.execute_script("""arguments[0].selected = true;""", firstOption)
                            
                except StaleElementReferenceException:
                    log.warning(f"Retrying due to stale element.")

                except Exception as e:
                    log.error(f"Select element error for question: {question}, answer: {answer}")
                    log.error(traceback.format_exc())  # Full traceback for better debugging

            else:
                log.info(f"Unable to determine field type for question: {question}, moving to next field.")



 
    def ans_question(self, question):  # refactor this to an ans.yaml file
        answer = None
        question = question.lower().strip()
        choices = ["6", "5", "4", "3"]

        # English proficiency-related questions
        if "english" in question:
            if "speak" in question or "communicate" in question:
                answer = "Yes"
            elif "proficiency" in question or "level" in question:
                answer = "Native"

        # Experience-related questions
        elif "how many" in question and ("experience" in question or "years" in question):
            answer = random.choice(choices)
        elif "do you" in question and "experience" in question:
            answer = "Yes"
        elif "how did you hear" in question:
            answer = "Other"
        elif "refer" in question or "referred" in question:
            answer = "N/A"
        elif "why are you seeking" in question or ("why" in question and "this position"):
            answer = "Good glassdoor reviews and the workers I talked to love their jobs"

        # Work authorization questions
        elif "work" in question and ("authorization" in question or "authorized" in question):
            if "usc" in question:
                answer = "USC: 0"
            elif "status" in question:
                answer = "U.S Citizen"
        elif "W2" in question:
            answer = "Yes"
        elif ("eligible" in question or "able" in question) and "clearance" in question:
            answer = "Yes"
        elif ("have" in question or "obtain" in question or "obtained" in question) and "clearance" in question:
            answer = "Yes"
        elif ("US" in question or "U.S." in question or "green" in question ) and ("citizen" in question or "card" in question):
            answer = "Yes"

        # Disability and drug test-related questions
        elif "do you" in question and "disability" in question:
            answer = "No"
        elif "drug test" in question:
            if "positive" in question:
                answer = "No"
            elif "can you" in question:
                answer = "Yes"

        # Commuting and legal questions
        elif "can you" in question and "commute" in question:
            answer = "Yes"
        elif "criminal" in question or "felon" in question or "charged" in question:
            answer = "No"

        # Other personal questions
        elif "currently reside" in question:
            answer = "Yes"
        elif "sponsor" in question:
            answer = "No"
        elif ("us citizen" in question or "u.s. citizen" in question) and "clearance" in question:
            answer = "Yes"
        elif "salary" in question:
            answer = self.salary
        elif "gender" in question:
            answer = "Male"
        elif "race" in question:
            answer = "White"
        elif "lgbtq" in question:
            answer = "No"
        elif "ethnicity" in question or "nationality" in question:
            answer = "White"
        elif "government" in question:
            answer = "I do not wish to self-identify"
        elif "are you legally" in question:
            answer = "Yes"


        # General affirmative questions
        elif "do you" in question or "did you" in question or "have you" in question or "are you" in question:
            answer = "Yes"

        # Default case for unanswered questions
        if answer is None:
            log.info("Not able to answer question automatically. Please provide answer")
            answer = "4"  # Placeholder for unanswered questions
            time.sleep(5)

        log.info("Answering question: " + question + " with answer: " + answer)

        # Append question and answer to the CSV
        if question not in self.answers:
            self.answers[question] = answer
            new_data = pd.DataFrame({"Question": [question], "Answer": [answer]})
            new_data.to_csv(self.qa_file, mode='a', header=False, index=False, encoding='utf-8')

        return answer


    def load_page(self, sleep=1):
        scroll_page = 0
        while scroll_page < 4000:
            self.browser.execute_script("window.scrollTo(0," + str(scroll_page) + " );")
            scroll_page += 500
            time.sleep(sleep)

        if sleep != 1:
            self.browser.execute_script("window.scrollTo(0,0);")
            time.sleep(sleep)

        page = BeautifulSoup(self.browser.page_source, "lxml")
        return page

    def avoid_lock(self) -> None:
        x, _ = pyautogui.position()
        pyautogui.moveTo(x + 200, pyautogui.position().y, duration=1.0)
        pyautogui.moveTo(x, pyautogui.position().y, duration=0.5)
        pyautogui.keyDown('ctrl')
        pyautogui.press('esc')
        pyautogui.keyUp('ctrl')
        time.sleep(0.5)
        pyautogui.press('esc')

    def next_jobs_page(self, position, location, jobs_per_page, experience_level=[], time_filter="24 hours"):
        # Construct the experience level part of the URL
        experience_level_str = ",".join(map(str, experience_level)) if experience_level else ""
        experience_level_param = f"&f_E={experience_level_str}" if experience_level_str else ""

        # Construct the time filter part of the URL
        if time_filter == "24 hours":
            time_posted_param = "&f_TPR=r86400"  # Last 24 hours
        elif time_filter == "past week":
            time_posted_param = "&f_TPR=r604800"  # Last week
        elif time_filter == "past month":
            time_posted_param = "&f_TPR=r2592000"  # Last month
        else:
            time_posted_param = ""  # No filter (Any time)

        self.browser.get(
            # URL for jobs page with Easy Apply, position, location, and time filter
            "https://www.linkedin.com/jobs/search/?f_LF=f_AL&keywords=" +
            position + location + "&start=" + str(jobs_per_page) + experience_level_param + time_posted_param
        )

        log.info(f"Loading next job page with time filter: {time_filter}")
        self.load_page()
        return (self.browser, jobs_per_page)



    # def finish_apply(self) -> None:
    #     self.browser.close()


if __name__ == '__main__':

    with open("config.yaml", 'r') as stream:
        try:
            parameters = yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            raise exc

    assert len(parameters['positions']) > 0
    assert len(parameters['locations']) > 0
    assert parameters['username'] is not None
    assert parameters['password'] is not None
    assert parameters['phone_number'] is not None


    if 'uploads' in parameters.keys() and type(parameters['uploads']) == list:
        raise Exception("uploads read from the config file appear to be in list format" +
                        " while should be dict. Try removing '-' from line containing" +
                        " filename & path")

    log.info({k: parameters[k] for k in parameters.keys() if k not in ['username', 'password']})

    output_filename: list = [f for f in parameters.get('output_filename', ['output.csv']) if f is not None]
    output_filename: list = output_filename[0] if len(output_filename) > 0 else 'output.csv'
    blacklist = parameters.get('blacklist', [])
    blackListTitles = parameters.get('blackListTitles', [])

    uploads = {} if parameters.get('uploads', {}) is None else parameters.get('uploads', {})
    for key in uploads.keys():
        assert uploads[key] is not None

    locations: list = [l for l in parameters['locations'] if l is not None]
    positions: list = [p for p in parameters['positions'] if p is not None]

    bot = EasyApplyBot(parameters['username'],
                       parameters['password'],
                       parameters['phone_number'],
                       parameters['salary'],
                       parameters['rate'], 
                       uploads=uploads,
                       filename=output_filename,
                       blacklist=blacklist,
                       blackListTitles=blackListTitles,
                       experience_level=parameters.get('experience_level', [])
                       )
    bot.start_apply(positions, locations)