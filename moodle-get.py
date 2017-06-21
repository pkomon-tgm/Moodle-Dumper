import requests
import os
import multiprocessing
import urllib.request
import time
import re


class MoodleResourceDumper(object):
    def __init__(self, base_url):
        self.session = requests.session()
        self.opener = None
        self.set_base_url(base_url)

    def set_base_url(self, base_url):
        self.base_url = base_url
        self.login_url = base_url + "login/index.php" if base_url[-1] == "/" else base_url + "/login/index.php"
        self.resource_url_template = base_url + "mod/resource/view.php?id=%i" if base_url[-1] == "/" \
            else base_url + "/mod/resource/view.php?id=%i"
        self.assign_url_template = base_url + "mod/assign/view.php?id=%i" if base_url[-1] == "/" \
            else base_url + "/mod/assign/view.php?id=%i"

    def login(self, username, password):
        if not isinstance(username, str) or not isinstance(password, str):
            raise TypeError()

        resp = self.session.post(self.login_url, data={"username": username, "password": password})

        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.session.cookies),
                                                  urllib.request.HTTPRedirectHandler())
        return resp

    def dump_resources(self, course_url, dir, allowed_file_exts=[]):
        """
        used to dump all resource-files of a moodle course into a directory

        :param course_url: the url of the course
        :param dir: the dir to dump to
        :param allowed_file_exts: the file extentions of the files to dump (empty means ALL)
        :return: None
        """
        response = self.session.get(course_url)

        if response.status_code != 200:
            raise ValueError()

        res_ids = self.__get_ids(response.text, "resource/view.php?id=")

        self.__get_and_write_all(res_ids, dir, allowed_file_exts)

    def dump_assign(self, course_url, dir, include_submission=False):
        """
        used to dump all resource-files of a moodle course into a directory

        :param course_url: the url of the course
        :param dir: the dir to dump to
        :param allowed_file_exts: the file extensions of the files to dump (empty means ALL)
        :return: None
        """
        response = self.session.get(course_url)

        if response.status_code != 200:
            raise ValueError()

        os.makedirs(dir, exist_ok=True)

        assign_ids = self.__get_ids(response.text, "assign/view.php?id=")

        self.__dump_assign_all([self.assign_url_template % assign_id for assign_id in assign_ids],
                               dir, include_submission)

        #self.__get_and_write_all(assign_ids, dir, allowed_file_exts)

    def __get_ids(self, course_page, search_str):
        """
        takes the raw html page of a moodle course, searches for resources and returns their ids

        :param course_page: the course page as string in plain html
        :search_str "resource/view.php?id=" for resources, "assign/view.php?id=" for assignments
        :return: list of the ids
        """
        res_ids = []

        # determine course content start and end positions
        content_start_at = course_page.find("<div id=\"content\"")  # current version of moodle
        if content_start_at == -1:
            content_start_at = course_page.find("<div id=\"page-content\"")  # moodle archives use this id!
        if content_start_at == -1:
            return []  # return empty list, no content was found

        next_div_end = course_page.find("</div", content_start_at)
        inner_div_start = course_page.find("<div", content_start_at + 1, next_div_end)
        while inner_div_start != -1:
            next_div_end = course_page.find("</div", next_div_end + 1)
            inner_div_start = course_page.find("<div", inner_div_start + 1, next_div_end)
        content_end_at = next_div_end

        found_res_at = course_page.find(search_str)
        while found_res_at != -1:
            found_res_end_at = course_page.find('"', found_res_at + len(search_str))

            id = course_page[found_res_at + len(search_str):found_res_end_at]

            #check if id position within course content
            if found_res_at > content_start_at and found_res_at < content_end_at:
                res_ids.append(int(id))
            elif found_res_at > content_end_at:
                break

            found_res_at = course_page.find(search_str, found_res_at + 1)

        return res_ids

    def __dump_assign_all(self, urls, dir, include_submission=False):
        with multiprocessing.Pool(len(urls)) as pool:
            pool.starmap(get_and_write_assign, [(self, url, dir, include_submission) for url in urls])

    def __get_and_write_all(self, res_ids, dir, allowed_file_exts=[]):
        """
        takes a list of resource ids, downloads the corresponding resources (files with extensions not allowed are
        ignored) and writes them to files within the directory handed (dir)

        for each resource id a new thread is spawned, handling download and writing. the method waits for all
        threads to finish!

        :param res_ids: list of resource ids
        :param dir: directory (string) to save the files to
        :param allowed_file_exts: extensions allowed, empty means ALL are allowed!
        :return: None
        """
        # make sure dir exists
        os.makedirs(dir, exist_ok=True)

        if res_ids:
            # create process for each resource
            with multiprocessing.Pool(len(res_ids)) as pool:
                pool.starmap(get_and_write_single, [(self, res_id, dir, allowed_file_exts) for res_id in res_ids])

    def get_redirected_url(self, url):
        request = self.opener.open(url)
        return request.url


def get_and_write_assign(moodle_res_dumper, url, dir, include_submission=False):
    print("trying to download and write contents of '%s'" % url)
    resp = moodle_res_dumper.session.get(url)
    title_start_at = resp.text.find("<h2>")+4
    name = resp.text[title_start_at:resp.text.find("<", title_start_at)]
    name = re.sub('[^a-zA-Z0-9.\n]', '_', name)

    if include_submission:
        dir = dir + "/" + name
        os.makedirs(dir, exist_ok=True)

    filename = dir + "/" + name + ".html"
    if resp.status_code == 200:
        write(resp, filename)
    print("writing to '" + filename + "' done!")

    if include_submission:
        submission_at = resp.text.find("submission_files/")
        if submission_at != -1:
            url_start = resp.text.rfind("http", 0, submission_at)
            url_end = resp.text.find("\"", url_start)
            url = resp.text[url_start:url_end]
            filename = dir + "/" + get_filename(url)
            print(url)
            resp = moodle_res_dumper.session.get(url)
            if resp.status_code == 200:
                write(resp, filename)
            print("writing to '" + filename + "' done!")


def get_and_write_single(moodle_res_dumper, res_id, dir, allowed_file_exts=[]):
    # check where https://elearning.tgm.ac.at/mod/resource/view.php?id=1234 redirect (to check file extension)
    print("checking url redirect for '%s'" % (moodle_res_dumper.resource_url_template % res_id))
    redirected_url = moodle_res_dumper.get_redirected_url(moodle_res_dumper.resource_url_template % res_id)

    # determine filename
    filename = dir + "/" + get_filename(redirected_url)

    # check extensions
    file_ext = filename[filename.rfind("."):len(filename)]

    if allowed_file_exts and file_ext not in allowed_file_exts:
        print("ignoring url '%s'" % redirected_url)
        print("ignoring files of that type ('%s')!" % file_ext)
        return

    print("downloading resource from %s ..." % moodle_res_dumper.resource_url_template % res_id)
    try:
        resp = moodle_res_dumper.session.get(moodle_res_dumper.resource_url_template % res_id, timeout=120)
    except:
        print("request to %s timed out" % moodle_res_dumper.resource_url_template % res_id)
        return
    print("downloading done, writing to file...")

    if resp.status_code == 200:
        write(resp, filename)
    print("writing to '" + filename + "' done!")


def write(resp, filename):
    with open(filename, 'wb') as fd:
        for chunk in resp.iter_content(chunk_size=128):
            fd.write(chunk)


def get_filename(url):
    url_has_params = url.find("?") != -1
    if url_has_params:
        return url[url.rfind("/")+1:url.rfind("?")]
    else:
        return url[url.rfind("/")+1:len(url)]


if __name__ == "__main__":

    username = "user"
    password = "pass"

    start = time.time()

    dumper = MoodleResourceDumper("https://elearning.tgm.ac.at/")
    dumper.login(username, password)
    dumper.dump_resources("https://elearning.tgm.ac.at/course/view.php?id=138", "sew5bhit/pdfs", [".pdf"])
    #dumper.dump_resources("https://elearning.tgm.ac.at/course/view.php?id=71", "syt5xhit/pdfs", [".pdf"])
    #dumper.dump_assign("https://elearning.tgm.ac.at/course/view.php?id=138", "sew5bhit/assignments", True)
    #dumper.dump_assign("https://elearning.tgm.ac.at/course/view.php?id=71", "syt5xhit/assignments", True)

    dumper.set_base_url("https://elearning.tgm.ac.at/archiv/")
    dumper.login(username, password)
    dumper.dump_resources("https://elearning.tgm.ac.at/archiv/course/view.php?id=1232", "sew4xhit/pdfs/ws", [".pdf"])
    dumper.dump_resources("https://elearning.tgm.ac.at/archiv/course/view.php?id=1362", "sew4xhit/pdfs/ss", [".pdf"])
    dumper.dump_resources("https://elearning.tgm.ac.at/archiv/course/view.php?id=706", "sew3bhit/pdfs", [".pdf"])

    dumper.session.close()

    end = time.time()
    delta = end - start
    print("took %i seconds" % delta)

    #todo error handling when unable to log in
    #todo write allowed extensions as kwargs
    #todo add ignored extensions kwarg