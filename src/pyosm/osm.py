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

    # def __getattr__(self, key):
    #     try:
    #         return self._record[key]
    #     except:
    #         raise AttributeError("%r object has no attribute %r" %
    #                              (type(self).__name__, key))

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
    def clear_cache(cls):
        cls.__cache__ = {}

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
            log.debug('Cache hit')
            #log.debug("Cache hit: ({0}) = {1}\n".format(k,
            #                                            cls.__cache__[k]))
            return cls.__cache__[k]

        #log.debug("Cache miss: ({0})\n"\
        #          "Keys: {1}\n".format(k,
        #                               cls.__cache__.keys()))

        return None

    @classmethod
    def __cache_set__(cls, url, data, value):
        cls.__cache__[url + repr(data)] = value

    def __call__(self, query, fields=None, authorising=False, clear_cache=False, debug=False):

        if clear_cache:
            self.clear_cache()

        url = self.BASE_URL + query

        values = {'apiid': self._auth.apiid,
                  'token': self._auth.token}

        if not authorising:
            values.update({'userid': self._auth.userid,
                           'secret': self._auth.secret})

        if fields:
            values.update(fields)

        if debug:
            log.debug("{0} {1}".format(url, values))

        data = urllib.urlencode(values)

        req = urllib2.Request(url, data)

        obj = self.__class__.__cache_lookup__(url, data)

        if not obj:

            response = urllib2.urlopen(req)

            result = response.read()

            
            # Crude test to see if the response is JSON
            # OSM returns a string as an error case.
            try:
                if result[0] not in ('[', '{'):
                    log.debug("{0} {1}".format(url, values))
                    raise OSMException(url, values, result)
            except IndexError:
                # This means that result is not a list
                log.debug("{0} {1}".format(url, values))
                log.error(repr(result))
                raise

            obj = json.loads(result)

            if 'error' in obj:
                log.debug("{0} {1}".format(url, values))
                raise OSMException(url, values, obj['error'])
            if 'err' in obj:
                log.debug("{0} {1}".format(url, values))
                raise OSMException(url, values, obj['err'])

            self.__class__.__cache_set__(url, data, obj)

        if debug:
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
    def __init__(self, osm, accessor, section, badge_type, details, structure):
        self._section = section
        self._badge_type = badge_type
        self.name = details['name']
        self.table = details['table']

        activities = {}
        if len(structure) > 1:
            for activity in [row['name'] for row in structure[1]['rows']]:
                activities[activity] = ''

        OSMObject.__init__(self, osm, accessor, activities)

    def get_members(self):
        url = "challenges.php?"\
            "&termid={0}" \
            "&type={1}" \
            "&sectionid={2}" \
            "&section={3}" \
            "&c={4}".format(self._section.term['termid'],
                            self._badge_type,
                            self._section['sectionid'],
                            self._section['section'],
                            self.name.lower())
        
        return [ OSMObject(self._osm,
                           self._accessor,
                           record) for record in \
                           self._accessor(url)['items'] ]

class Badges(OSMObject):
    def __init__(self, osm, accessor, record, section, badge_type):
        self._section = section
        self._badge_type = badge_type
        self._order = record['badgeOrder']
        self._details = record['details']
        self._stock = record['stock']
        self._structure = record['structure']

        badges = {}
        for badge in self._details.keys():
            badges[badge] = Badge(osm, accessor,
                                  self._section,
                                  self._badge_type,
                                  self._details[badge],
                                  self._structure[badge])

        OSMObject.__init__(self, osm, accessor, badges)


class Member(OSMObject):

    def __init__(self, osm, section, accessor, column_map, record):
        OSMObject.__init__(self, osm, accessor, record)

        self._section = section
        self._column_map = column_map
        for k, v in self._column_map.items():
            self._column_map[k] = v.replace(' ', '')

        self._reverse_column_map = dict((reversed(list(i)) for i in column_map.items()))
        self._changed_keys = []

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
            if key not in self._changed_keys:
                self._changed_keys.append(key)
        except:
            try:
                self._record[self._reverse_column_map[key]] = value
                if self._reverse_column_map[key] not in self._changed_keys:
                    self._changed_keys.append(self._reverse_column_map[key])
 
            except:
                raise KeyError("%r object has no attribute %r" %
                               (type(self).__name__, key))

            raise KeyError("%r object has no attribute %r" %
                           (type(self).__name__, key))

    # def remove(self, last_date):
    #     """Remove the member record."""
    #     delete_url='users.php?action=deleteMember&type=leaveremove&section={0}'
    #     delete_url = delete_url.format(self._section.section)
    #     fields={ 'scouts': ["{0}".format(self.scoutid),],
    #              'sectionid': self._section.sectionid,
    #              'date': last_date }
        
    #     self._accessor(delete_url, fields, clear_cache=True, debug=True)

    def save(self):
        """Write the member to the section."""
        update_url='users.php?action=updateMember&dateFormat=generic'
        patrol_url='users.php?action=updateMemberPatrol'
        create_url='users.php?action=newMember'

        if self['scoutid'] == '':
            # create
            fields = {}
            for key in self._changed_keys:
                fields[key] = self._record[key]
            fields['sectionid'] = self._section['sectionid']
            record = self._accessor(create_url, fields, clear_cache=True, debug=True)
            self['scoutid'] = record['scoutid']
        else:
            # update
            fields = {}
            for key in self._changed_keys:
                fields[key] = self._record[key]

            result = True
            for key in fields:
                record = self._accessor(update_url, 
                                        { 'scoutid': self['scoutid'],
                                          'column': self._reverse_column_map[key],
                                          'value': fields[key],
                                          'sectionid': self._section['sectionid'] }, 
                                        clear_cache=True, debug=True)
                if record[self._reverse_column_map[key]] != fields[key]:
                    result = False

            # TODO handle change to grouping.

            return result

    def get_badges(self):
        "Return a list of badges objects for this member."

        ret = []
        for i in self._section.challenge.values():
            ret.extend( [ badge for badge in badge.get_members() \
                          if badge['scoutid'] == self['scoutid'] ] )
        return ret
        
        
class Members(OSMObject):
    DEFAULT_DICT = {  u'address': '',
                      u'address2': '',
                      u'age': u'',
                      u'custom1': '',
                      u'custom2': '',
                      u'custom3': '',
                      u'custom4': '',
                      u'custom5': '',
                      u'custom6': '',
                      u'custom7': '',
                      u'custom8': '',
                      u'custom9': '',
                      u'dob': u'',
                      u'email1': '',
                      u'email2': '',
                      u'email3': '',
                      u'email4': '',
                      u'ethnicity': '',
                      u'firstname': u'',
                      u'joined': u'',
                      u'joining_in_yrs': u'',
                      u'lastname': u'',
                      u'medical': '',
                      u'notes': '',
                      u'parents': '',
                      u'patrol': u'',
                      u'patrolid': u'',
                      u'patrolleader': u'',
                      u'phone1': '',
                      u'phone2': '',
                      u'phone3': '',
                      u'phone4': '',
                      u'religion': '',
                      u'school': '',
                      u'scoutid': u'',
                      u'started': u'',
                      u'subs': '',
                      u'type': u'',
                      u'yrs': 0}

    def __init__(self, osm, section, accessor, column_map, record):
        self._osm = osm,
        self._section = section
        self._accessor = accessor,
        self._column_map = column_map
        self._identifier = record['identifier']

        members = {}
        for member in record['items']:
            members[member[self._identifier]] = Member(osm, section, accessor, column_map, member)

        OSMObject.__init__(self, osm, accessor, members)

    def new_member(self, firstname, lastname, dob, startedsection, started):
        new_member = Member(self._osm, self._section,
                            self._accessor,self._column_map,self.DEFAULT_DICT)
        new_member['firstname'] = firstname
        new_member['lastname'] = lastname
        new_member['dob'] = dob
        new_member['startedsection'] = startedsection
        new_member['started'] = started
        new_member['patrolid'] = '-1'
        new_member['patrolleader'] = '0'
        new_member['phone1'] = ''
        new_member['email1'] = ''
        return new_member

class Section(OSMObject):
    def __init__(self, osm, accessor, record):
        OSMObject.__init__(self, osm, accessor, record)

        try:
            self._member_column_map = record['sectionConfig']['columnNames']
        except KeyError:
            log.debug("No extra member columns.")
            self._member_column_map = {}

        self.terms = [term for term in osm.terms(self['sectionid'])
                      if term.is_active()]

        # TODO - report error if terms has more than one entry.
        self.term = self.terms[0]

        self.challenge = self._get_badges('challenge')
        self.activity = self._get_badges('activity')
        self.staged = self._get_badges('staged')
        self.core = self._get_badges('core')
        self.members = self._get_members()

    def __repr__(self):
        return 'Section({0}, "{1}", "{2}")'.format(
            self['sectionid'],
            self['sectionname'],
            self['section'])

    def _get_badges(self, badge_type):
        url = "challenges.php?action=getInitialBadges" \
              "&type={0}" \
              "&sectionid={1}" \
              "&section={2}" \
              "&termid={3}" \
            .format(badge_type, 
                    self['sectionid'],
                    self['section'],
                    self.term['termid'])

        return Badges(self._osm, self._accessor,
                      self._accessor(url), self, badge_type)

    def events(self):
        pass

    def _get_members(self):
        url = "users.php?&action=getUserDetails" \
              "&sectionid={0}" \
              "&termid={1}" \
              "&dateFormat=uk" \
              "&section={2}" \
            .format(self['sectionid'],
                    self.term['termid'],
                    self['section'])

        return Members(self._osm, self, self._accessor,
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
            self.sections[section['sectionid']] = section
            if section['isDefault'] == u'1':
                self.section = section

        log.info("Default section = {0}, term = {1}".format(
            self.section['sectionname'],
            self.section.term['name']))

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


    osm = OSM(auth)

    log.debug('Sections - {0}\n'.format(osm.sections))


    test_section = '15797'
    for badge in osm.sections[test_section].challenge.values():
        log.debug('{0}'.format(badge._record))
              
    #members = osm.sections[test_section].members

    #    member = members[members.keys()[0]]
    #member['special'] = 'changed'
    #member.save()
    
    #new_member = members.new_member('New First 2','New Last 2','02/09/2004','02/12/2012','02/11/2012')
    
    #log.debug("New member = {0}: {1}".format(new_member.firstname,new_member.lastname))
    #new_member.save()

    
        
    #for k,v in osm.sections['14324'].members.items():
    #    log.debug("{0}: {1} {2} {3}".format(k,v.firstname,v.lastname,v.TermtoScouts))

    #for k,v in osm.sections['14324'].activity.items():
    #    log.debug("{0}: {1}".format(k,v.keys()))


    #pp.pprint(osm.sections['14324'].members())
    #for k,v in osm.sections['14324'].challenge.items():
    #    log.debug("{0}: {1}".format(k,v.keys()))


    Accessor.__cache_save__(open(DEF_CACHE, 'w'))
