"""Online Scout Manager Interface.

Usage:
  osm.py <command>...
  osm.py (-a | --authorise) email password
  osm.py (-h | --help)
  osm.py --version

Options:
  -h --help      Show this screen.
  --version      Show version.
  -a --authorise Request authorisation credentials.
"""
from docopt import docopt

import urllib
import urllib2
import json

class Accessor:

    BASE_URL = "https://www.onlinescoutmanager.co.uk"
    
    def __init__(self, authorisor):
        self._auth = authorisor

    def __call__(self, query, fields, authorising=False):

        values = { 'apiid' : self._auth.apiid,
                   'token' : self._auth.token}

        if not authorising:
            values.update('userid': self._auth.userid,
                          'secret': self._auth.secret }

        
        values.update(fields)
        
        data = urllib.urlencode(values)

        req = urllib2.Request(self.BASE_URL+query, data)
        
        response = urllib2.urlopen(req)

        result = response.read()

        return json.loads("".join(result.readlines()))
        
class Authorisor:

    def __init__(self, apiid, token):
        self.apiid = apiid
        self.token = token

        self.userid = None
        self.secret = None
        
    def authorise(self, email, password):
        fields = {'email': email,
                  'password': password}

        accessor = Accessor(self)
        creds = accessor("users.php?action=authorise", fields, authorising=True)

        self.userid = creds.userid
        self.secret = creds.secret
        
    def save_to_file(self, dest):
        dest.write(self.userid+'\n')
        dest.write(self.secret+'\n')

    def read_from_file(self, src):
        self.userid = src.readline()[:-1]
        self.secret = src.readline()[:-1]
        

class OSM:

    def __init__(self, authorisor):
        self._accessor = Accessor(authorisor)
        
                 
                 
