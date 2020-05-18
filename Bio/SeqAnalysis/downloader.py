import os
import re
from multiprocessing.pool import ThreadPool
from os.path import isfile, join
from time import time as timer
from typing import Union, List, Tuple
from urllib import request, error

from Bio import Entrez
from Bio import SeqIO


class SeqDownloader:
    """
    SeqDownloader class is responsible for downloading fasta files for Uniprot/NCBI IDs
    corresponding to given list or single ID ensuring their uniqueness.
    """

    def __init__(self, full_list: Union[str, List], directory: str):
        """
        In several steps, __init__ method is downloading and saving multiple fasta files in a short period of time:
        1) Checks if the parameters are of the correct type, if not, raises exceptions
        2) Checks if directories needed for proper file organization exists, if not, creates them
        3) Prepares list of urls based on the list of IDs from which files will be obtained
        4) Downloads and saves files using multiprocessing
        5) Saves database in one fasta file ready for parse by SeqIO module. Also saves additional outputs which are
           text files that contains entries not downloaded either because of being obsolete or due to http errors

        :param full_list: Either List of IDs or single str.
        :param directory: str given by user to organize files properly.

        :raises: Exception when variables are not of the expected type.

        """
        if isinstance(full_list, str):
            clear_ids = [full_list]
        elif isinstance(full_list, List):
            clear_ids = full_list
        else:
            raise Exception("Given variable is not either str or List.")
        if isinstance(directory, str):
            analysis_dir = directory
        else:
            raise Exception("Your directory name is not str.")

        clear_ids = list(dict.fromkeys(clear_ids))

        for list_element in clear_ids:
            if isinstance(list_element, str):
                pass
            else:
                raise Exception("At least one element of your IDs list is not str.")

        print("Number of unique IDs: {0}".format(len(clear_ids)))
        print("Name of the current batch of files: {0}".format(analysis_dir))

        print("------------------------------------Directory check------------------------------------------")

        dirs = ['Downloads', 'Failed', 'Database']
        for single_dir in dirs:
            self.mk_dirs(single_dir)
        self.mk_subdirs(analysis_dir)

        obsolete = []
        http_error = []

        print("--------------------------------------Downloading--------------------------------------------")

        urls = self.paths_and_urls(clear_ids, analysis_dir)

        print("Downloading files. Please wait...")

        ThreadPool(20).imap_unordered(self.fetch_url, urls)
        start = timer()
        for entry in urls:
            self.fetch_url(entry, obsolete, http_error)

        Entrez.email = ''
        for idx in clear_ids:
            if re.match(r'([A-Z]){2,3}\w+', idx):
                self.download_ncbi(idx, analysis_dir, obsolete, http_error)

        obsolete = list(dict.fromkeys(obsolete))

        mypath = ('./Downloads/{0}'.format(analysis_dir))
        only_files = [f for f in os.listdir(mypath) if isfile(join(mypath, f))]
        files_no_ext = [".".join(f.split(".")[:-1]) for f in os.listdir(mypath) if os.path.isfile(join(mypath, f))]

        total_number = len(only_files)
        print("Download of " + str(total_number) + f" took {timer() - start} seconds")

        print("-------------------------------------Saving outputs------------------------------------------")
        print('Possibly obsolete entries were saved in Failed/{0}/Obsolete.txt'.format(analysis_dir))
        print('Number of obsolete entries: {0}'.format(str(len(obsolete))))

        with open('./Failed/{0}/Obsolete.txt'.format(analysis_dir), 'w+') as obs:
            for item in obsolete:
                obs.write(item + '\n')

        print('Entries with possible download error were saved in Failed/{0}/Error.txt'.format(analysis_dir))
        print('Number of download error entries: {0}'.format(str(len(http_error))))

        with open('./Failed/{0}/Error.txt'.format(analysis_dir), 'w+') as fail:
            for item in http_error:
                fail.write(item + '\n')

        print("Creating database. Please wait...")
        for file in only_files:
            with open('./Downloads/{0}/{1}'.format(analysis_dir, file)) as big_fasta:
                one_fasta = big_fasta.read()
                with open('./Database/{0}.fasta'.format(analysis_dir), 'a+') as data:
                    data.write(one_fasta + '\n')

        print("Your sequences were saved in Database/{0}.fasta".format(analysis_dir))
        print("Done.")
        self.downloaded_files = files_no_ext

    @staticmethod
    def read_list_of_ids(file: str) -> List:
        """
        Reads given file and creates List with unique IDs.

        :param file: str, name of file.
        :raise: Exception when can't find a file.
        :return: List with IDs.
        """
        try:
            data = ''
            with open(file, 'r') as f:
                for line in f.readlines():
                    line = re.sub('[!@/#$|:]', ' ', line).strip()
                    # Substitutes above signs with space ensuring your
                    # file with IDs will be always read correctly.
                    data = data + ' ' + line
                data = data.split()
                data = list(dict.fromkeys(data))
            return data
        except FileNotFoundError:
            raise Exception("!!!ERROR!!! \n"
                            "Please enter right name of file (with .txt).\n"
                            "Remember that your ID file should be in the same directory as this script.\n"
                            "If not please specify path to the ID file.\n"
                            "E.g. dir1/subdir1/list.txt")

    @staticmethod
    def mk_dirs(dir_name: str):
        if not os.path.exists(dir_name):
            os.mkdir(dir_name)
            print("Directory {0} status: created".format(dir_name))
        else:
            print("Directory {0} status: already exists".format(dir_name))

    @staticmethod
    def mk_subdirs(dir_name: str):
        if not os.path.exists('./Downloads/{0}/'.format(dir_name)):
            os.mkdir('./Downloads/{0}/'.format(dir_name))
            print("Directory Downloads/{0} status: created".format(dir_name))
        else:
            print("Directory Downloads/{0} status: already exists".format(dir_name))
        if not os.path.exists('./Failed/{0}/'.format(dir_name)):
            os.mkdir('./Failed/{0}/'.format(dir_name))
            print("Directory Failed/{0} status: created".format(dir_name))
        else:
            print("Directory Failed/{0} status: already exists".format(dir_name))

    @staticmethod
    def paths_and_urls(ids: List, cdir: str) -> List:
        """
        Creates List of tuples with the path where the file will be saved and url from which it will be fetched.

        :param ids: List with IDs, given by user.
        :param cdir: str, name of the directory where the analysis is currently being carried out.
        :return: List of tuples.
        """
        pu = []
        for idx in ids:
            if re.match(r'([A-Z]){1}\d+', idx):
                path_url = tuple([('./Downloads/{0}/{1}.fasta'.format(cdir, idx)),
                                  ('https://www.uniprot.org/uniprot/' + idx + '.fasta')])
                pu.append(path_url)

        return pu

    @staticmethod
    def fetch_url(entry: Tuple, obs: List, http: List) -> str:
        """
        Fetching files from given urls, then saving in the indicated directory. In case of http error
        or after confirming that entry is obsolete, appends currently handled ID to the appropriate list.

        :param entry: Tuple from paths_and_urls method.
        :param obs: List of obsolete entries.
        :param http: List of entries failed to download due to http errors.
        :return: str, path were the file will be saved.
        """
        path, url = entry
        uniprot_id = re.sub('[/.]', ' ', path).strip().split()
        if not os.path.exists(path):
            try:
                fasta = request.urlopen(url)
                fasta = fasta.read().decode()

                if fasta == '':
                    obs.append(uniprot_id[2])
                else:
                    with open(path, 'w+') as f:
                        f.write(fasta)

            except error.HTTPError or TimeoutError or error.URLError:
                http.append(uniprot_id[2])
        return path

    @staticmethod
    def download_ncbi(ncbi_id: str, cdir: str, obs: List, http: List):
        """
        Fetching files using NCBI IDs in Entrez module and saving them in the indicated directory. In case of http error
        or after confirming that entry is obsolete, appends currently handled ID to the appropriate list.

        :param ncbi_id: str, ID confirmed to be from the NCBI database.
        :param cdir: str, name of the directory where the analysis is currently being carried out.
        :param obs: List of obsolete entries.
        :param http: List of entries failed to download due to http errors.
        """
        try:
            handle = Entrez.efetch(db="protein", id=ncbi_id, rettype="fasta", retmode="text")
            record = handle.read()

            if record == '':
                obs.append(ncbi_id)
            else:
                with open('./Downloads/{0}/{1}.fasta'.format(cdir, ncbi_id), 'w+') as f:
                    f.write(record)

        except error.HTTPError or TimeoutError or error.URLError:
            http.append(ncbi_id)


class SeqDatabase:
    """
    SeqDatabase class is responsible for creating and giving you access to Dict containing IDs and SeqRecord objects.
    """

    def __init__(self, full_list: Union[str, List], directory: str):
        """
        Uses SeqDownloader class to download desired fasta files and then SeqIO module to create Dict with ID of fasta
        file as key and SeqRecord object as vaule.

        :param full_list: Either List of IDs or single str.
        :param directory: str given by user to organize files properly.

        """
        download = SeqDownloader(full_list, directory)
        seq_data = {}
        for index, record in zip(download.downloaded_files,
                                 SeqIO.parse("./Database/{0}.fasta".format(directory), "fasta")):
            if index not in seq_data.keys():
                seq_data[index] = record
        self.database = seq_data

    def get(self, indexes: Union[str, List] = None) -> List:
        """
        Allows user to get desired record or list of records data.

        :param indexes: str or List with IDs corresponding to records that user would like to get
        :raises: Exception when variables are not of the expected type.
        :return: List of SeqRecord objects
        """
        if indexes is None:
            records = list(self.database.values())
        else:
            if isinstance(indexes, str):
                keys = [indexes]
            elif isinstance(indexes, List):
                keys = indexes
            else:
                raise Exception("Given variable is not either str or List.")
            records = [self.database.get(key) for key in keys]
        return records
