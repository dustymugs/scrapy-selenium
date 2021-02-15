"""This module contains the ``SeleniumMiddleware`` scrapy middleware"""

from importlib import import_module
import random
import time
import urllib3

from scrapy import signals
from scrapy.exceptions import NotConfigured
from scrapy.http import HtmlResponse
from selenium.webdriver.support.ui import WebDriverWait

from .http import SeleniumRequest

class SeleniumMiddleware:
    """Scrapy middleware handling the requests using selenium"""

    def __init__(
        self,
        driver_name,
        driver_executable_path,
        browser_executable_path,
        command_executor,
        driver_arguments,
        driver_preferences,
        driver_profile,
        concurrent_requests,
        concurrent_requests_per_domain,
    ):
        """Initialize the selenium webdriver

        Parameters
        ----------
        driver_name: str
            The selenium ``WebDriver`` to use
        driver_executable_path: str
            The path of the executable binary of the driver
        driver_arguments: list
            A list of arguments to initialize the driver
        driver_preferences: dict
            A dictionary of key/value preferences for the driver
        driver_profile: dict
            A string for the Directory of profile to clone for the driver
        browser_executable_path: str
            The path of the executable binary of the browser
        command_executor: str
            Selenium remote server endpoint
        """

        webdriver_base_path = f'selenium.webdriver.{driver_name}'

        driver_klass_module = import_module(f'{webdriver_base_path}.webdriver')
        driver_klass = getattr(driver_klass_module, 'WebDriver')

        driver_options_module = import_module(f'{webdriver_base_path}.options')
        driver_options_klass = getattr(driver_options_module, 'Options')

        driver_options = driver_options_klass()

        if browser_executable_path:
            driver_options.binary_location = browser_executable_path
        for argument in driver_arguments:
            driver_options.add_argument(argument)
        if driver_name == 'firefox':
            for k, v in driver_preferences.items():
                driver_options.set_preference(k, v)

        self._command_executor = command_executor
        self._driver_name = driver_name
        self._driver_klass = driver_klass
        self._driver_kwargs = {
            'executable_path': driver_executable_path,
            f'{driver_name}_options': driver_options,
        }
        if driver_name == 'firefox':
            if driver_profile is not None:
            self._driver_kwargs['firefox_profile'] = driver_profile

        self.replace_driver()

    def replace_driver(self):
        if hasattr(self, 'driver'):
            self.driver.delete_all_cookies()
            self.driver.quit()

        # locally installed driver
        if self._driver_kwargs['executable_path'] is not None:
            self.driver = self._driver_klass(**self._driver_kwargs)
            self.driver.set_window_size(
                random.uniform(1920 * 0.5, 1920),
                random.uniform(1080 * 0.5, 1080),
            )

            # we replace the default PoolManager
            self.driver.command_executor._conn.clear()
            self.driver.command_executor._conn = urllib3.PoolManager(
                timeout=self.driver.command_executor._timeout,
                maxsize=1,
                block=False,
            )
        # remote driver
        elif self._command_executor is not None:
            from selenium import webdriver
            capabilities = self._driver_kwargs[f'{self._driver_name_options}'].to_capabilities()
            self.driver = webdriver.Remote(
                command_executor=self._command_executor,
                desired_capabilities=capabilities
            )

        self.driver.replace_driver = self.replace_driver

        return self.driver

    @classmethod
    def from_crawler(cls, crawler):
        """Initialize the middleware with the crawler settings"""

        driver_name = crawler.settings.get('SELENIUM_DRIVER_NAME')
        driver_executable_path = crawler.settings.get('SELENIUM_DRIVER_EXECUTABLE_PATH')
        browser_executable_path = crawler.settings.get('SELENIUM_BROWSER_EXECUTABLE_PATH')
        command_executor = crawler.settings.get('SELENIUM_COMMAND_EXECUTOR')
        driver_arguments = crawler.settings.get('SELENIUM_DRIVER_ARGUMENTS')
        driver_preferences = crawler.settings.get('SELENIUM_DRIVER_PREFERENCES')
        driver_profile = crawler.settings.get('SELENIUM_DRIVER_PROFILE')
        concurrent_requests = crawler.settings.getint('CONCURRENT_REQUESTS')
        concurrent_requests_per_domain = crawler.settings.getint('CONCURRENT_REQUESTS_PER_DOMAIN')

        if driver_name is None:
            raise NotConfigured('SELENIUM_DRIVER_NAME must be set')

        if driver_executable_path is None and command_executor is None:
            raise NotConfigured('Either SELENIUM_DRIVER_EXECUTABLE_PATH '
                                'or SELENIUM_COMMAND_EXECUTOR must be set')

        middleware = cls(
            driver_name=driver_name,
            driver_executable_path=driver_executable_path,
            browser_executable_path=browser_executable_path,
            command_executor=command_executor,
            driver_arguments=driver_arguments,
            driver_preferences=driver_preferences,
            driver_profile=driver_profile,
            concurrent_requests=concurrent_requests,
            concurrent_requests_per_domain=concurrent_requests_per_domain,
        )

        crawler.signals.connect(middleware.spider_closed, signals.spider_closed)

        return middleware

    def process_request(self, request, spider):
        """Process a request using the selenium driver if applicable"""

        if not isinstance(request, SeleniumRequest):
            return None

        delay = spider.settings.getint('DOWNLOAD_DELAY')
        randomize_delay = spider.settings.getbool('RANDOMIZE_DOWNLOAD_DELAY')
        if delay:
            if randomize_delay:
                delay = random.uniform(0.5 * delay, 1.5 * delay)
            time.sleep(delay)

        for cookie_name, cookie_value in request.cookies.items():
            self.driver.add_cookie(
                {
                    'name': cookie_name,
                    'value': cookie_value
                }
            )

        self.driver.get(request.url)

        if request.wait_until:
            WebDriverWait(self.driver, request.wait_time).until(
                request.wait_until
            )

        if request.screenshot:
            request.meta['screenshot'] = self.driver.get_screenshot_as_png()

        if request.script:
            self.driver.execute_script(request.script)

        body = str.encode(self.driver.page_source)

        # Expose the driver via the "meta" attribute
        request.meta.update({'driver': self.driver})

        return HtmlResponse(
            self.driver.current_url,
            body=body,
            encoding='utf-8',
            request=request
        )

    def spider_closed(self):
        """Shutdown the driver when spider is closed"""

        self.driver.quit()
