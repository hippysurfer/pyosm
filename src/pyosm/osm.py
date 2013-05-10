# coding=utf-8
"""Online Scout Manager Interface.

Usage:
  osm.py <apiid> <token>
  osm.py <apiid> <token> run <query>
  osm.py <apiid> <token> -a <email> <password>
  osm.py (-h | --help)
  osm.py --version


Options:
  -h --help      Show this screen.
  --version      Show version.
  -a             Request authorisation credentials.

"""

from docopt import docopt

import sys
import urllib
import urllib2
import json
import pickle
import logging
import datetime
import pprint
import collections

log = logging.getLogger(__name__)
pp = pprint.PrettyPrinter(indent=4)

DEF_CACHE = "osm.cache"
DEF_CREDS = "osm.creds"


class OSMException(Exception):
    def __init__(self, url, values, error):
        self._url = url
        self._values = values
        self._error = error

    def __str__(self):
        return "OSM API Error from {0}:\n" \
               "values = {1}\n" \
               "result = {2}".format(self._url,
                                     self._values,
                                     self._error)


class OSMObject(collections.MutableMapping):
    def __init__(self, osm, accessor, record):
        self._osm = osm
        self._accessor = accessor
        self._record = record

    def __getattr__(self, key):
        try:
            return self._record[key]
        except:
            raise AttributeError("%r object has no attribute %r" %
                                 (type(self).__name__, key))

    def __getitem__(self, key):
        try:
            return self._record[key]
        except:
            raise KeyError("%r object has no attribute %r" %
                           (type(self).__name__, key))

    def __setitem__(self, key, value):
        try:
            self._record[key] = value
        except:
            raise KeyError("%r object has no attribute %r" %
                           (type(self).__name__, key))

    def __delitem__(self, key):
        try:
            del (self._record[key])
        except:
            raise KeyError

    def __len__(self):
        return len(self._record)

    def __iter__(self):
        return self._record.__iter__()


class Accessor(object):
    __cache__ = {}

    BASE_URL = "https://www.onlinescoutmanager.co.uk/"

    def __init__(self, authorisor):
        self._auth = authorisor

    @classmethod
    def __cache_save__(cls, cache_file):
        pickle.dump(cls.__cache__, cache_file)

    @classmethod
    def __cache_load__(cls, cache_file):
        cls.__cache__ = pickle.load(cache_file)

    @classmethod
    def __cache_lookup__(cls, url, data):
        k = url + repr(data)
        if k in cls.__cache__:
            log.debug("Cache hit: ({0}) = {1}\n".format(k,
                                                        cls.__cache__[k]))
            return cls.__cache__[k]

        log.debug("Cache miss: ({0})\n"\
                  "Keys: {1}\n".format(k,
                                       cls.__cache__.keys()))

        return None

    @classmethod
    def __cache_set__(cls, url, data, value):
        cls.__cache__[url + repr(data)] = value

    def __call__(self, query, fields=None, authorising=False):

        url = self.BASE_URL + query

        values = {'apiid': self._auth.apiid,
                  'token': self._auth.token}

        if not authorising:
            values.update({'userid': self._auth.userid,
                           'secret': self._auth.secret})

        if fields:
            values.update(fields)

        data = urllib.urlencode(values)

        req = urllib2.Request(url, data)

        obj = self.__class__.__cache_lookup__(url, data)

        if not obj:

            response = urllib2.urlopen(req)

            result = response.read()

            # Crude test to see if the response is JSON
            # OSM returns a string as an error case.
            if result[0] not in ('[', '{'):
                raise OSMException(url, values, result)

            obj = json.loads(result)

            if 'error' in obj:
                raise OSMException(url, values, obj['error'])
            if 'err' in obj:
                raise OSMException(url, values, obj['err'])

            self.__class__.__cache_set__(url, data, obj)

        log.debug(pp.pformat(obj))
        return obj


class Authorisor(object):
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

        self.userid = creds['userid']
        self.secret = creds['secret']

    def save_to_file(self, dest):
        dest.write(self.userid + '\n')
        dest.write(self.secret + '\n')

    def load_from_file(self, src):
        self.userid = src.readline()[:-1]
        self.secret = src.readline()[:-1]


class Term(OSMObject):
    def __init__(self, osm, accessor, record):
        OSMObject.__init__(self, osm, accessor, record)

        self.startdate = datetime.datetime.strptime(record[u'startdate'],
                                                    '%Y-%m-%d')

        self.enddate = datetime.datetime.strptime(record[u'enddate'],
                                                  '%Y-%m-%d')

    def is_active(self):
        now = datetime.datetime.now()
        return (self.startdate < now) and (self.enddate > now)


class Badge(OSMObject):
    def __init__(self, osm, accessor, details, structure):
        self.name = details['name']
        self.table = details['table']

        activities = {}
        if len(structure) > 1:
            for activity in [row['name'] for row in structure[1]['rows']]:
                activities[activity] = ''

        OSMObject.__init__(self, osm, accessor, activities)


class Badges(OSMObject):
    def __init__(self, osm, accessor, record):
        self._order = record['badgeOrder']
        self._details = record['details']
        self._stock = record['stock']
        self._structure = record['structure']

        badges = {}
        for badge in self._details.keys():
            badges[badge] = Badge(osm, accessor,
                                  self._details[badge],
                                  self._structure[badge])

        OSMObject.__init__(self, osm, accessor, badges)


class Member(OSMObject):
    def __init__(self, osm, accessor, column_map, record):
        OSMObject.__init__(self, osm, accessor, record)

        self._column_map = column_map
        for k, v in self._column_map.items():
            self._column_map[k] = v.replace(' ', '')

        self._reverse_column_map = dict((reversed(list(i)) for i in column_map.items()))

    def __getattr__(self, key):
        try:
            return self._record[key]
        except:

            try:
                return self._record[self._reverse_column_map[key]]
            except:
                raise AttributeError("%r object has no attribute %r" %
                                     (type(self).__name__, key))

    def __getitem__(self, key):
        try:
            return self._record[key]
        except:
            try:
                return self._record[self._reverse_column_map[key]]
            except:
                raise KeyError("%r object has no attribute %r" %
                               (type(self).__name__, key))


    def __setitem__(self, key, value):
        try:
            self._record[key] = value
        except:
            try:
                self._record[self._reverse_column_map[key]] = value
            except:
                raise KeyError("%r object has no attribute %r" %
                               (type(self).__name__, key))

            raise KeyError("%r object has no attribute %r" %
                           (type(self).__name__, key))


class Members(OSMObject):
    def __init__(self, osm, accessor, column_map, record):
        self._identifier = record['identifier']

        members = {}
        for member in record['items']:
            members[member[self._identifier]] = Member(osm, accessor, column_map, member)

        OSMObject.__init__(self, osm, accessor, members)


class Section(OSMObject):
    def __init__(self, osm, accessor, record):
        OSMObject.__init__(self, osm, accessor, record)

        self._member_column_map = record['sectionConfig']['columnNames']

        self.terms = [term for term in osm.terms(self.sectionid)
                      if term.is_active()]

        # TODO - report error if terms has more than one entry.
        self.term = self.terms[0]

        self.challenge = self._get_badges('challenge')
        self.activity = self._get_badges('activity')
        self.staged = self._get_badges('staged')
        self.core = self._get_badges('core')
        self.members = self._get_members()

    def __repr__(self):
        return 'Section({0}, "{1}", "{2}")'.format(self.sectionid,
                                                   self.sectionname,
                                                   self.section)

    def _get_badges(self, badge_type):
        url = "challenges.php?action=getInitialBadges" \
              "&type={0}" \
              "&sectionid={s.sectionid}" \
              "&section={s.section}" \
              "&termid={s.term.termid}" \
            .format(badge_type, s=self)

        return Badges(self._osm, self._accessor, self._accessor(url))

    def events(self):
        pass

    def _get_members(self):
        url = "users.php?&action=getUserDetails" \
              "&sectionid={s.sectionid}" \
              "&termid={s.term.termid}" \
              "&dateFormat=uk" \
              "&section={s.section}" \
            .format(s=self)

        return Members(self._osm, self._accessor,
                       self._member_column_map, self._accessor(url))


class OSM(object):
    def __init__(self, authorisor):
        self._accessor = Accessor(authorisor)

        self.sections = {}
        self.section = None

        self.init()

    def init(self):
        roles = self._accessor('api.php?action=getUserRoles')

        self.sections = {}

        for section in [Section(self, self._accessor, role)
                        for role in roles
                        if 'section' in role]:
            self.sections[section.sectionid] = section
            if section.isDefault == u'1':
                self.section = section

        log.info("Default section = {0}, term = {1}".format(
            self.section.sectionname,
            self.section.term.name))

    def terms(self, sectionid):
        return [Term(self, self._accessor, term) for term \
                in self._accessor('api.php?action=getTerms')[sectionid]]


if __name__ == '__main__':

    logging.basicConfig(level=logging.DEBUG)
    log.debug("Debug On\n")

    try:
        Accessor.__cache_load__(open(DEF_CACHE, 'r'))
    except:
        log.debug("Failed to load cache file\n")

    args = docopt(__doc__, version='OSM 2.0')
    print args
    if args['-a']:
        auth = Authorisor(args['<apiid>'], args['<token>'])
        auth.authorise(args['<email>'],
                       args['<password>'])
        auth.save_to_file(open(DEF_CREDS, 'w'))
        sys.exit(0)

    auth = Authorisor(args['<apiid>'], args['<token>'])
    auth.load_from_file(open(DEF_CREDS, 'r'))

    if args['run']:
        accessor = Accessor(auth)

        pp.pprint(accessor(args['<query>']))


    #osm = OSM(auth)

    #log.debug('Sections - {0}\n'.format(osm.sections))


    #for k,v in osm.sections['14324'].members.items():
    #    log.debug("{0}: {1} {2} {3}".format(k,v.firstname,v.lastname,v.TermtoScouts))

    #for k,v in osm.sections['14324'].activity.items():
    #    log.debug("{0}: {1}".format(k,v.keys()))


    #pp.pprint(osm.sections['14324'].members())
    #for k,v in osm.sections['14324'].challenge.items():
    #    log.debug("{0}: {1}".format(k,v.keys()))


    Accessor.__cache_save__(open(DEF_CACHE, 'w'))
