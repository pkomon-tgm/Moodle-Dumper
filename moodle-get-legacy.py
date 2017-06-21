import requests
import os
import threading
import urllib.request
import time


class MoodleResourceDumper(object):
    #you will need to change this when dumping files from moodle archives (https://elearning.tgm.ac.at/archiv/...)
    res_template = "https://elearning.tgm.ac.at/mod/resource/view.php?id=%i"
    login_url = "https://elearning.tgm.ac.at/login/index.php"

    def __init__(self):
        self.session = requests.session()
        self.opener = None

    def login(self, username, password, url=login_url):
        if not isinstance(url, str) or not isinstance(url, str) or not isinstance(url, str):
            raise TypeError()

        resp = self.session.post(url, data={"username": username, "password": password})

        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.session.cookies),
                                                  urllib.request.HTTPRedirectHandler())
        return resp

    def dump_resources(self, course_url, dir, allowed_file_exts=[]):
        '''
        used to dump all resource-files of a moodle course into a directory
        :param course_url: the url of the course
        :param dir: the dir to dump to
        :param allowed_file_exts: the file extentions of the files to dump (empty means ALL)
        :return: None
        '''
        response = self.session.get(course_url)

        if response.status_code != 200:
            raise ValueError()

        res_ids = self.__get_res_ids(response.text)

        self.__get_and_write(res_ids, dir, allowed_file_exts)

    def __get_res_ids(self, course_page):
        '''
        takes the raw html page of a moodle course, searches for resources and returns their ids
        :param course_page: the course page as string in plain html
        :return: list of the resource ids
        '''
        res_ids = []
        resource_string = "resource/view.php?id="
        found_res_at = course_page.find(resource_string)

        while found_res_at != -1:
            found_res_end_at = course_page.find('"', found_res_at + len(resource_string))

            id = course_page[found_res_at + len(resource_string):found_res_end_at]
            res_ids.append(int(id))

            found_res_at = course_page.find(resource_string, found_res_at + 1)

        return res_ids

    def __get_and_write(self, res_ids, dir, allowed_file_exts=[]):
        '''
        takes a list of resource ids, downloads the corresponding resources (files with extensions not allowed are
        ignored) and writes them to files within the directory handed (dir)
        for each resource id a new thread is spawned, handling download and writing. the method waits for all
        threads to finish!
        :param res_ids: list of resource ids
        :param dir: directory (string) to save the files to
        :param allowed_file_exts: extensions allowed, empty means ALL are allowed!
        :return: None
        '''
        # make sure dir exists
        try:
            os.mkdir(dir)
        except FileExistsError:
            pass

        # create thread for each resource
        threads = []
        for res_id in res_ids:
            get_and_write_thread = GetAndWriteThread(self.session, self.opener, res_id, dir, allowed_file_exts)
            get_and_write_thread.start()
            threads.append(get_and_write_thread)

        # join threads
        for t in threads:
            t.join()


class GetAndWriteThread(threading.Thread):
    """
    Thread for downloading a file to a corresponding resource id
    """
    def __init__(self, session, opener, res_id, dir, allowed_file_exts):
        super().__init__()
        self.__session = session
        self.__opener = opener
        self.__res_id = res_id
        self.__allowed_file_exts = allowed_file_exts
        self.__dir = dir

    def run(self):
        #check where https://elearning.tgm.ac.at/mod/resource/view.php?id=1234 redirect (to check file extension)
        print("checking url redirect for '%s'" % MoodleResourceDumper.res_template % self.__res_id)
        redirected_url = self.__get_redirected_url(MoodleResourceDumper.res_template % self.__res_id)

        #determine filename
        url_has_params = redirected_url.find("?") != -1
        if url_has_params:
            filename = self.__dir + redirected_url[redirected_url.rfind("/"):redirected_url.rfind("?")]
        else:
            filename = self.__dir + redirected_url[redirected_url.rfind("/"):len(redirected_url)]

        #check extensions
        file_ext = filename[filename.rfind("."):len(filename)]

        if self.__allowed_file_exts and file_ext not in self.__allowed_file_exts:
            print("ignoring url '%s'" % redirected_url)
            print("ignoring files of that type ('%s')!" % file_ext)
            return

        print("downloading resource with from %s ..." % MoodleResourceDumper.res_template % self.__res_id)
        try:
            resp = self.__session.get(MoodleResourceDumper.res_template % self.__res_id, timeout=120)
        except:
            print("request to %s timed out" % MoodleResourceDumper.res_template % self.__res_id)
            return
        print("downloading done, writing to file...")

        if resp.status_code == 200:
            with open(filename, 'wb') as fd:
                for chunk in resp.iter_content(chunk_size=128):
                    fd.write(chunk)
        print("writing to '" + filename + "' done!")

    def __get_redirected_url(self, url):
        request = self.__opener.open(url)
        return request.url

if __name__ == "__main__":

    username = "pkomon"
    password = "Newschool5" #maybe use input instead of storing a password in a plain text file?

    start = time.time()

    dumper = MoodleResourceDumper()
    dumper.login(username, password)
    #course url, directory to write to, file extensions to include (empty means ALL)
    dumper.dump_resources("https://elearning.tgm.ac.at/course/view.php?id=138", "sew5bhit_pdfs", [".pdf"])
    dumper.dump_resources("https://elearning.tgm.ac.at/course/view.php?id=71", "syt5xhit_pdfs", [".pdf"])
    dumper.session.close()

    end = time.time()
    delta = end - start
    print("took %i seconds" % delta)