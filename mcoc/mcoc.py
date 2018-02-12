import re
from datetime import datetime, timedelta
from textwrap import wrap
from collections import UserDict, defaultdict, Mapping, namedtuple, OrderedDict
from functools import partial
from math import log2
from math import *
from operator import attrgetter
import os
import time
import inspect
import aiohttp
import logging
import csv
import json
import pygsheets
import random

from pygsheets.utils import numericise_all
import asyncio
from .utils.dataIO import dataIO
from functools import wraps
import discord
from discord.ext import commands
from .utils import chat_formatting as chat
from __main__ import send_cmd_help
from cogs.utils import checks
#from .hook import ChampionRoster, HashtagRankConverter
# from .hook import PagesMenu

## experimental jjw
import matplotlib.pyplot as plt

logger = logging.getLogger('red.mcoc')
logger.setLevel(logging.INFO)

class TitleError(Exception):
    def __init__(self, champ):
        self.champ = champ

data_files = {
    'spotlight': {'remote': 'https://docs.google.com/spreadsheets/d/1I3T2G2tRV05vQKpBfmI04VpvP5LjCBPfVICDmuJsjks/pub?gid=0&single=true&output=csv',
                'local': 'data/mcoc/spotlight_data.csv', 'update_delta': 1},
    'crossreference': {'remote': 'https://docs.google.com/spreadsheets/d/1WghdD4mfchduobH0me4T6IvhZ-owesCIyLxb019744Y/pub?gid=0&single=true&output=csv',
                'local': 'data/mcoc/crossreference.csv', 'update_delta': 1},
    'prestigeCSV':{'remote': 'https://docs.google.com/spreadsheets/d/1I3T2G2tRV05vQKpBfmI04VpvP5LjCBPfVICDmuJsjks/pub?gid=1346864636&single=true&output=csv',
                'local': 'data/mcoc/prestige.csv', 'update_delta': 1},
    'duelist' : {'remote': 'https://docs.google.com/spreadsheets/d/e/2PACX-1vTsPSNaY6WbNF1fY49jqjRm9hJZ60Sa6fU6Yd_t7nOrIxikVj-Y7JW_YSPwHoJfix9MA4YgWSenIwfl/pub?gid=694495962&single=true&output=csv',
                'local': 'data/mcoc/duelist.csv', 'update_delta': 1},
    #'masteries' : {'remote':'https://docs.google.com/spreadsheets/d/1mEnMrBI5c8Tbszr0Zne6qHkW6WxZMXBOuZGe9XmrZm8/pub?gid=0&single=true&output=csv',
                #'local': 'data/mcoc/masteries.csv', 'update_delta': 1},
    }

GS_BASE='https://sheets.googleapis.com/v4/spreadsheets/{}/values/{}?key=AIzaSyBugcjKbOABZEn-tBOxkj0O7j5WGyz80uA&majorDimension=ROWS'
SPOTLIGHT_DATASET='https://docs.google.com/spreadsheets/d/e/2PACX-1vRFLWYdFMyffeOzKiaeQeqoUgaESknK-QpXTYV2GdJgbxQkeCjoSajuLjafKdJ5imE1ADPYeoh8QkAr/pubhtml?gid=1483787822&single=true'
SPOTLIGHT_SURVEY='https://docs.google.com/forms/d/e/1FAIpQLSe4JYzU5CsDz2t0gtQ4QKV8IdVjE5vaxJBrp-mdfKxOG8fYiA/viewform?usp=sf_link'
PRESTIGE_SURVEY='https://docs.google.com/forms/d/e/1FAIpQLSeo3YhZ70PQ4t_I4i14jX292CfBM8DMb5Kn2API7O8NAsVpRw/viewform?usp=sf_link'
COLLECTOR_ICON='https://images-ext-1.discordapp.net/external/drzqadqtDB3udEqQ-wOcOfNLZFpF7HR05_iiTieI2uQ/https/raw.githubusercontent.com/JasonJW/mcoc-cogs/master/mcoc/data/portraits/portrait_collector.png'

local_files = {
    'sig_coeff': 'data/mcoc/sig_coeff.csv',
    'effect_keys': 'data/mcoc/effect_keys.csv',
    'signature': 'data/mcoc/signature.json',
    'synergy': 'data/mcoc/synergy.json',
}

async def postprocess_sig_data(bot, struct):
    sigs = load_kabam_json(kabam_bcg_stat_en)
    mcoc = bot.get_cog('MCOC')
    missing = []
    for key in struct.keys():
        champ_class = mcoc.champions.get(key.lower(), None)
        if champ_class is None:
            continue
        try:
            struct[key]['kabam_text'] = champ_class.get_kabam_sig_text(
                    champ_class, sigs=sigs,
                    champ_exceptions=struct['kabam_key_override'])
        except TitleError as e:
            missing.append(e.champ)
    if missing:
        bot.say("Skipped Champs due to Kabam Key Errors: {}".format(', '.join(missing)))

gapi_service_creds = 'data/mcoc/mcoc_service_creds.json'
gsheet_files = {
    'signature': {'gkey': '1kNvLfeWSCim8liXn6t0ksMAy5ArZL5Pzx4hhmLqjukg',
            'local': local_files['signature'],
            'postprocess': postprocess_sig_data,
            },
    #'spotlight': {'gkey': '1I3T2G2tRV05vQKpBfmI04VpvP5LjCBPfVICDmuJsjks',
            #'local': 'data/mcoc/spotlight_test.json',
            #},
    #'crossreference': {'gkey': '1WghdD4mfchduobH0me4T6IvhZ-owesCIyLxb019744Y',
            #'local': 'data/mcoc/xref_test.json',
            #},
    'synergy': {'gkey': '1Apun0aUcr8HcrGmIODGJYhr-ZXBCE_lAR7EaFg_ZJDY',
            'local': local_files['synergy'],
            },
}

star_glyph = '★'
lolmap_path='data/mcoc/maps/lolmap.png'
file_checks_json = 'data/mcoc/file_checks.json'
remote_data_basepath = 'https://raw.githubusercontent.com/JasonJW/mcoc-cogs/master/mcoc/data/'
icon_sdf = 'https://raw.githubusercontent.com/JasonJW/mcoc-cogs/master/mcoc/data/sdf_icon.png'

###### KEYS for MCOC JSON Data Extraction
mcoc_dir='data/mcoc/json/snapshots/en/'
kabam_bio = mcoc_dir + 'character_bios_en.json'
kabam_special_attacks = mcoc_dir+'special_attacks_en.json'
kabam_bcg_stat_en = mcoc_dir+'bcg_stat_en.json'
kabam_bcg_en= mcoc_dir+'bcg_en.json'
kabam_masteries=mcoc_dir+'masteries_en.json'
##### Special attacks require:
## mcoc_files + mcoc_special_attack + <champ.mcocjson> + {'_0','_1','_2'} ---> Special Attack title
#mcoc_special_attack='ID_SPECIAL_ATTACK_'
## mcoc_files mcoc_special_attack_desc + <champ.mcocjson> + {'_0','_1','_2'} ---> Special Attack Short description
#mcoc_special_attack_desc='ID_SPECIAL_ATTACK_DESCRIPTION_'


class_color_codes = {
        'Cosmic': discord.Color(0x2799f7), 'Tech': discord.Color(0x0033ff),
        'Mutant': discord.Color(0xffd400), 'Skill': discord.Color(0xdb1200),
        'Science': discord.Color(0x0b8c13), 'Mystic': discord.Color(0x7f0da8),
        'All': discord.Color(0xffffff), 'default': discord.Color.light_grey(),
        }
class_emoji = {
        'All':'<:all2:339511715920084993>',
        'Cosmic':'<:cosmic2:339511716104896512>',
        'Tech':'<:tech2:339511716197171200>',
        'Mutant':'<:mutant2:339511716201365514>',
        'Skill':'<:skill2:339511716549230592>',
        'Science':'<:science2:339511716029267969>',
        'Mystic':'<:mystic2:339511716150771712>',
        }

def from_flat(flat, ch_rating):
    denom = 5 * ch_rating + 1500 + flat
    return round(100*flat/denom, 2)

def to_flat(per, ch_rating):
    num = (5 * ch_rating + 1500) * per
    return round(num/(100-per), 2)

class QuietUserError(commands.UserInputError):
    pass

class AmbiguousArgError(QuietUserError):
    pass

class ChampConverter(commands.Converter):
    '''Argument Parsing class that geneartes Champion objects from user input'''

    arg_help = '''
    Specify a single champion with optional parameters of star, rank, or sig.
    Champion names can be a number of aliases or partial aliases if no conflicts are found.

    The optional arguments can be in any order, with or without spaces.
        <digit>* specifies star <default: 4>
        r<digit> specifies rank <default: 5>
        s<digit> specifies signature level <default: 99>

    Examples:
        4* yj r4 s30  ->  4 star Yellowjacket rank 4/40 sig 30
        r35*im        ->  5 star Ironman rank 3/45 sig 99
        '''
#(?:(?:s(?P<sig>[0-9]{1,3})) |(?:r(?P<rank>[1-5]))|(?:(?P<star>[1-5])\\?\*)|(?:d(?P<debug>[0-9]{1,2})))(?=\b|[a-zA-Z]|(?:[1-5]\\?\*))
    _bare_arg = None
    parse_re = re.compile(r'''(?:s(?P<sig>[0-9]{1,3}))
                             |(?:r(?P<rank>[1-5]))
                             |(?:(?P<star>[1-6])\\?\*)
                             |(?:d(?P<debug>[0-9]{1,2}))''', re.X)
    async def convert(self):
        bot = self.ctx.bot
        attrs = {}
        if self._bare_arg:
            args = self.argument.rsplit(' ', maxsplit=1)
            if len(args) > 1 and args[-1].isdecimal():
                attrs[self._bare_arg] = int(args[-1])
                self.argument = args[0]
        arg = ''.join(self.argument.lower().split(' '))
        for m in self.parse_re.finditer(arg):
            attrs[m.lastgroup] = int(m.group(m.lastgroup))
        token = self.parse_re.sub('', arg)
        if not token:
            err_str = "No Champion remains from arg '{}'".format(self.argument)
            await bot.say(err_str)
            raise commands.BadArgument(err_str)
        return (await self.get_champion(bot, token, attrs))

    async def get_champion(self, bot, token, attrs):
        mcoc = bot.get_cog('MCOC')
        try:
            champ = await mcoc.get_champion(token, attrs)
        except KeyError:
            champs = await mcoc.search_champions('.*{}.*'.format(token), attrs)
            if len(champs) == 1:
                await bot.say("'{}' was not exact but found close alternative".format(
                        token))
                champ = champs[0]
            elif len(champs) > 1:
                em = discord.Embed(title='Ambiguous Argument "{}"'.format(token),
                        description='Resolved to multiple possible champs')
                for champ in champs:
                    em.add_field(name=champ.full_name, inline=False,
                            value=chat.box(', '.join(champ.alias_set)))
                await bot.say(embed=em)
                raise AmbiguousArgError('Multiple matches for arg "{}"'.format(token))
            else:
                err_str = "Cannot resolve alias for '{}'".format(token)
                await bot.say(err_str)
                raise commands.BadArgument(err_str)
        return champ

class ChampConverterSig(ChampConverter):
    _bare_arg = 'sig'
    arg_help = ChampConverter.arg_help + '''
    Bare Number argument for this function is sig level:
        "yjr5s30" is equivalent to "yjr5 30"'''

class ChampConverterRank(ChampConverter):
    _bare_arg = 'rank'
    arg_help = ChampConverter.arg_help + '''
    Bare Number argument for this function is rank:
        "yjr5s30" is equivalent to "yjs30 5"'''

class ChampConverterStar(ChampConverter):
    _bare_arg = 'star'
    arg_help = ChampConverter.arg_help + '''
    Bare Number argument for this function is star:
        "5*yjr5s30" is equivalent to "yjr5s30 5"'''

class ChampConverterDebug(ChampConverter):
    _bare_arg = 'debug'

class ChampConverterMult(ChampConverter):

    arg_help = '''
    Specify multiple champions with optional parameters of star, rank, or sig.
    Champion names can be a number of aliases or partial aliases if no conflicts are found.

    The optional arguments can be in any order.
        <digit>* specifies star <default: 4>
        r<digit> specifies rank <default: 5>
        s<digit> specifies signature level <default: 99>

    If optional arguments are listed without a champion, it changes the default for all
    remaining champions.  Arguments attached to a champion are local to that champion
    only.

    Examples:
        s20 yj im        ->  4* Yellowjacket r5/50 sig 20, 4* Ironman r5/50 sig 20
        r35*ims20 ims40  ->  5 star Ironman r3/45 sig 20, 4* Ironman r5/50 sig 40
        r4s20 yj ims40 lc -> 4* Yellowjacket r4/40 sig 20, 4* Ironman r4/40 sig 40, 4* Luke Cage r4/40 sig 20
        '''

    async def convert(self):
        bot = self.ctx.bot
        champs = []
        default = {}
        dangling_arg = None
        for arg in self.argument.lower().split(' '):
            attrs = default.copy()
            for m in self.parse_re.finditer(arg):
                attrs[m.lastgroup] = int(m.group(m.lastgroup))
            token = self.parse_re.sub('', arg)
            if token != '':
                champ = await self.get_champion(bot, token, attrs)
                dangling_arg = None
                champs.append(champ)
            else:
                default.update(attrs)
                dangling_arg = arg
        if dangling_arg:
            em = discord.Embed(title='Dangling Argument',
                    description="Last argument '{}' is unused.\n".format(dangling_arg)
                        + "Place **before** the champion or **without a space**.")
            await bot.say(embed=em)
        return champs

class GSExport():

    def __init__(self, bot, gc, *, gkey, local, **kwargs):
        self.bot = bot
        self.gc = gc
        self.gkey = gkey
        self.local = local
        self.meta_sheet = kwargs.pop('meta_sheet', 'meta_sheet')
        for k,v in kwargs.items():
            setattr(self, k, v)
        self.data = defaultdict(partial(defaultdict, dict))

    async def retrieve_data(self):
        ss = self.gc.open_by_key(self.gkey)
        try:
            meta = ss.worksheet('title', self.meta_sheet)
        except pygsheets.WorksheetNotFound:
            await self.retrieve_sheet(ss, sheet_name=None, sheet_action='file', data_type='dict')
        else:
            for record in meta.get_all_records():
                await self.retrieve_sheet(ss, **record)
        if hasattr(self, 'postprocess'):
            await self.postprocess(self.bot, self.data)
        if self.local:
            dataIO.save_json(self.local, self.data)
        return self.data

    async def retrieve_sheet(self, ss, *, sheet_name, sheet_action, data_type, **kwargs):
        if sheet_name:
            sheet = ss.worksheet('title', sheet_name)
        else:
            sheet = ss.sheet1
            sheet_name = sheet.title
        if 'range' in kwargs and kwargs['range']:
            rng = self.bound_range(sheet, kwargs['range'])
            data = sheet.get_values(*rng, returnas='matrix',
                    #include_empty=kwargs['include_empty'])
                    include_empty=False)
        else:
            data = sheet.get_all_values(include_empty=False)
            #data = sheet.get_all_values(include_empty=kwargs['include_empty'])
        #data = sheet.get_all_values(include_empty=False)
        header = data[0]
        if data_type.startswith('nested_list'):
            data_type, dlen = data_type.rsplit('::', maxsplit=1)
            dlen = int(dlen)

        prep_func = getattr(self, kwargs.get('prepare_function', 'do_nothing'))
        if sheet_action == 'table':
            self.data[sheet_name] = [header]
        for row in data[1:]:
            drow = numericise_all(prep_func(row), '')
            rkey = drow[0]
            if sheet_action == 'merge':
                if data_type == 'nested_dict':
                    pack = dict(zip(header[2:], drow[2:]))
                    self.data[rkey][sheet_name][drow[1]] = pack
                    continue
                if data_type == 'list':
                    pack = drow[1:]
                elif data_type == 'nested_list':
                    if len(drow[1:]) < dlen or not any(drow[1:]):
                        pack = None
                    else:
                        pack = [drow[i:i+dlen] for i in range(1, len(drow), dlen)]
                self.data[rkey][sheet_name] = pack
            elif sheet_action in ('dict', 'file'):
                if data_type == 'list':
                    pack = drow[1:]
                elif data_type == 'dict':
                    pack = dict(zip(header, drow))
                if data_type == 'nested_dict':
                    pack = dict(zip(header[2:], drow[2:]))
                    self.data[sheet_name][rkey][drow[1]] = pack
                elif sheet_action == 'dict':
                    self.data[sheet_name][rkey] = pack
                elif sheet_action == 'file':
                    self.data[rkey] = pack
            elif sheet_action == 'table':
                self.data[sheet_name].append(drow)

    @staticmethod
    def bound_range(sheet, rng_str):
        rng = rng_str.split(':')
        rows = (1, sheet.rows)
        for i in range(2):
            if not rng[i][-1].isdigit():
                rng[i] = '{}{}'.format(rng[i], rows[i])
        return rng

    @staticmethod
    def do_nothing(row):
        return row

    @staticmethod
    def remove_commas(row):
        return [cell.replace(',', '') for cell in row]

    @staticmethod
    def remove_NA(row):
        return [None if cell in ("#N/A", "") else cell for cell in row]


class AliasDict(UserDict):
    '''Custom dictionary that uses a tuple of aliases as key elements.
    Item addressing is handled either from the tuple as a whole or any
    element within the tuple key.
    '''
    def __getitem__(self, key):
        if key in self.data:
            return self.data[key]
        for k in self.data.keys():
            if key in k:
                return self.data[k]
        raise KeyError("Invalid Key '{}'".format(key))

class ChampionFactory():
    '''Creation and storage of the dynamically created Champion subclasses.
    A new subclass is created for every champion defined.  Then objects are
    created from user function calls off of the dynamic classes.'''

    def __init__(self, *args, **kwargs):
        self.cooldown_delta = 5 * 60
        self.cooldown = time.time() - self.cooldown_delta - 1
        self.needs_init = True
        super().__init__(*args, **kwargs)
        self.bot.loop.create_task(self.update_local())  # async init
        logger.debug('ChampionFactory Init')

    def data_struct_init(self):
        logger.info('Preparing data structures')
        self._prepare_aliases()
        self._prepare_prestige_data()
        self.needs_init = False

    async def update_local(self):
        now = time.time()
        if now - self.cooldown_delta < self.cooldown:
            return
        self.cooldown = now
        is_updated = await self.verify_cache_remote_files()
        if is_updated or self.needs_init:
            self.data_struct_init()

    def create_champion_class(self, bot, alias_set, **kwargs):
        kwargs['bot'] = bot
        kwargs['alias_set'] = alias_set
        kwargs['klass'] = kwargs.pop('class', 'default')

        kwargs['full_name'] = kwargs['champ']
        kwargs['bold_name'] = chat.bold(' '.join(
                [word.capitalize() for word in kwargs['full_name'].split(' ')]))
        kwargs['class_color'] = class_color_codes[kwargs['klass']]
        kwargs['class_icon'] = class_emoji[kwargs['klass']]

        kwargs['class_tags'] = {'#' + kwargs['klass'].lower()}
        for a in kwargs['abilities'].split(','):
            kwargs['class_tags'].add('#' + ''.join(a.lower().split(' ')))
        for a in kwargs['hashtags'].split('#'):
            kwargs['class_tags'].add('#' + ''.join(a.lower().split(' ')))
        for a in kwargs['extended_abilities'].split(','):
            kwargs['class_tags'].add('#' + ''.join(a.lower().split(' ')))
        for a in kwargs['counters'].split(','):
            kwargs['class_tags'].add('#!' + ''.join(a.lower().split(' ')))
        if kwargs['class_tags']:
            kwargs['class_tags'].difference_update({'#'})

        for key, value in kwargs.items():
            if not value or value == 'n/a':
                kwargs[key] = None

        champion = type(kwargs['mattkraftid'], (Champion,), kwargs)
        self.champions[tuple(alias_set)] = champion
        logger.debug('Creating Champion class {}'.format(kwargs['mattkraftid']))
        return champion

    async def get_champion(self, name_id, attrs=None):
        '''straight alias lookup followed by new champion object creation'''
        #await self.update_local()
        return self.champions[name_id](attrs)

    async def search_champions(self, search_str, attrs=None):
        '''searching through champion aliases and allowing partial matches.
        Returns an array of new champion objects'''
        #await self.update_local()
        re_str = re.compile(search_str)
        champs = []
        for champ in self.champions.values():
            if any([re_str.search(alias) is not None
                    for alias in champ.alias_set]):
                champs.append(champ(attrs))
        return champs

    async def verify_cache_remote_files(self, verbose=False, force_cache=False):
        logger.info('Check remote files')
        if os.path.exists(file_checks_json):
            try:
                file_checks = dataIO.load_json(file_checks_json)
            except:
                file_checks = {}
        else:
            file_checks = {}
        async with aiohttp.ClientSession() as s:
            is_updated = False
            for key in data_files.keys():
                if key in file_checks:
                    last_check = datetime(*file_checks.get(key))
                else:
                    last_check = None
                remote_check = await self.cache_remote_file(key, s, verbose=verbose,
                        last_check=last_check)
                if remote_check:
                    is_updated = True
                    file_checks[key] = remote_check.timetuple()[:6]
        dataIO.save_json(file_checks_json, file_checks)
        return is_updated

    async def cache_remote_file(self, key, session, verbose=False, last_check=None,
                force_cache=False):
        dargs = data_files[key]
        strf_remote = '%a, %d %b %Y %H:%M:%S %Z'
        response = None
        remote_check = False
        now = datetime.now()
        if os.path.exists(dargs['local']) and not force_cache:
            if last_check:
                check_marker = now - timedelta(days=dargs['update_delta'])
                refresh_remote_check = check_marker > last_check
            else:
                refresh_remote_check = True
            local_dt = datetime.fromtimestamp(os.path.getmtime(dargs['local']))
            if refresh_remote_check:
                response = await session.get(dargs['remote'])
                if 'Last-Modified' in response.headers:
                    remote_dt = datetime.strptime(response.headers['Last-Modified'], strf_remote)
                    remote_check = now
                    if remote_dt < local_dt:
                        # Remote file is older, so no need to transfer
                        response = None
        else:
            response = await session.get(dargs['remote'])
        if response and response.status == 200:
            logger.info('Caching ' + dargs['local'])
            with open(dargs['local'], 'wb') as fp:
                fp.write(await response.read())
            remote_check = now
            await response.release()
        elif response:
            err_str = "HTTP error code {} while trying to Collect {}".format(
                    response.status, key)
            logger.error(err_str)
            await response.release()
        elif verbose and remote_check:
            logger.info('Local file up-to-date:', dargs['local'], now)
        return remote_check

    def _prepare_aliases(self):
        '''Create a python friendly data structure from the aliases json'''
        logger.debug('Preparing aliases')
        self.champions = AliasDict()
        raw_data = load_csv(data_files['crossreference']['local'])
        punc_strip = re.compile(r'[\s)(-]')
        champs = []
        all_aliases = set()
        id_index = raw_data.fieldnames.index('status')
        alias_index = raw_data.fieldnames[:id_index]
        for row in raw_data:
            if all([not i for i in row.values()]):
                continue    # empty row check
            alias_set = set()
            for col in alias_index:
                if row[col]:
                    alias_set.add(row[col].lower())
            alias_set.add(punc_strip.sub('', row['champ'].lower()))
            if all_aliases.isdisjoint(alias_set):
                all_aliases.union(alias_set)
            else:
                raise KeyError("There are aliases that conflict with previous aliases."
                        + "  First occurance with champ {}.".format(row['champ']))
            self.create_champion_class(self.bot, alias_set, **row)

    def _prepare_prestige_data(self):
        logger.debug('Preparing prestige')
        mattkraft_re = re.compile(r'(?P<star>\d)-(?P<champ>.+)-(?P<rank>\d)')
        with open(data_files['prestigeCSV']['local'], newline='') as csvfile:
            reader = csv.reader(csvfile)
            for row in reader:
                champ_match = mattkraft_re.fullmatch(row.pop(0))
                if not champ_match:
                    continue
                name = champ_match.group('champ')
                star = int(champ_match.group('star'))
                rank = int(champ_match.group('rank'))

                champ = self.champions.get(name)
                if not champ:
                    logger.info('Skipping ' + name)
                    continue

                sig_len = 201 if star >= 5 else 100
                sig = [0] * sig_len
                for i, v in enumerate(row):
                    try:
                        if v and i < sig_len:
                            sig[i] = int(v)
                    except:
                        print(name, i, v, len(sig))
                        raise
                if not hasattr(champ, 'prestige_data'):
                    champ.prestige_data = {4: [None] * 5, 5: [None] * 5,6: [None] * 5, 3: [None] * 4, 2: [None]*3, 1: [None]*2}
                try:
                    champ.prestige_data[star][rank-1] = sig
                except:
                    print(name, star, rank, len(champ.prestige_data),
                            len(champ.prestige_data[star]))
                    raise

def command_arg_help(**cmdkwargs):
    def internal_func(f):
        helps = []
        for param in inspect.signature(f).parameters.values():
            if issubclass(param.annotation, commands.Converter):
                arg_help = getattr(param.annotation, 'arg_help')
                if arg_help is not None:
                    helps.append(arg_help)
        if helps:
            if f.__doc__:
                helps.insert(0, f.__doc__)
            f.__doc__ = '\n'.join(helps)
        @wraps(f)
        async def wrapper(*args, **kwargs):
            return await f(*args, **kwargs)
        return commands.command(**cmdkwargs)(wrapper)
    return internal_func

class MCOC(ChampionFactory):
    '''A Cog for Marvel's Contest of Champions'''

    def __init__(self, bot):
        self.bot = bot

        self.settings = {
                'siglvl': 1,
                'sigstep': 20,
                'table_width': 9,
                'sig_inc_zero': False,
                }
        self.data_dir='data/mcoc/{}/'
        self.shell_json=self.data_dir + '{}.json'
        self.split_re = re.compile(', (?=\w+:)')
        logger.info("MCOC Init")
        super().__init__()

    @commands.command(aliases=('p2f',), hidden=True)
    async def per2flat(self, per: float, ch_rating: int=100):
        '''Convert Percentage to MCOC Flat Value'''
        await self.bot.say(to_flat(per, ch_rating))

    @commands.command(name='flat', aliases=('f2p'))
    async def flat2per(self, *, m):
        '''Convert MCOC Flat Value to Percentge
        <equation> [challenger rating = 100]'''
        if ' ' in m:
            m, cr = m.rsplit(' ',1)
            challenger_rating = int(cr)
        else:
            challenger_rating = 100
        m = ''.join(m)
        math_filter = re.findall(r'[\[\]\-()*+/0-9=.,% ]' +
            r'|acos|acosh|asin|asinh' +
            r'|atan|atan2|atanh|ceil|copysign|cos|cosh|degrees|e|erf|erfc|exp' +
            r'|expm1|fabs|factorial|floor|fmod|frexp|fsum|gamma|gcd|hypot|inf' +
            r'|isclose|isfinite|isinf|isnan|round|ldexp|lgamma|log|log10|log1p' +
            r'|log2|modf|nan|pi|pow|radians|sin|sinh|sqrt|tan|tanh', m)
        flat_val = eval(''.join(math_filter))
        p = from_flat(flat_val, challenger_rating)
        em = discord.Embed(color=discord.Color.gold(),
                title='FlatValue:',
                description='{}'.format(flat_val))
        em.add_field(name='Percentage:', value='{}\%'.format(p))
        await self.bot.say(embed=em)

    @commands.command(aliases=('compf','cfrac'), hidden=True)
    async def compound_frac(self, base: float, exp: int):
        '''Calculate multiplicative compounded fractions'''
        if base > 1:
            base = base / 100
        compound = 1 - (1 - base)**exp
        em = discord.Embed(color=discord.Color.gold(),
            title="Compounded Fractions",
            description='{:.2%} compounded {} times'.format(base, exp))
        em.add_field(name='Expected Chance', value='{:.2%}'.format(compound))
        await self.bot.say(embed=em)

    @commands.command(aliases=('update_mcoc','mu','um',), hidden=True)
    async def mcoc_update(self, fname, force=False):
        if len(fname) > 3:
            for key in data_files.keys():
                if key.startswith(fname):
                    fname = key
                    break
        if fname in data_files:
            async with aiohttp.ClientSession() as s:
                await self.cache_remote_file(fname, s, force_cache=True, verbose=True)
        else:
            await self.bot.say('Valid options for 1st argument are one of (or initial portion of)\n\t'
                    + '\n\t'.join(data_files.keys()))
            return

        self.data_struct_init()
        await self.bot.say('Summoner, I have Collected the data')

    async def say_user_error(self, msg):
        em = discord.Embed(color=discord.Color.gold(), title=msg)
        await self.bot.say(embed=em)

    @commands.command(hidden=True)
    async def mcocset(self, setting, value):
        if setting in self.settings:
            self.settings[setting] = int(value)

    @commands.command(hidden=True, aliases=['cg',])
    async def cache_gsheets(self, key=None):
        await self.update_local()
        try:
            gc = pygsheets.authorize(service_file=gapi_service_creds, no_cache=True)
        except FileNotFoundError:
            await self.bot.say('Cannot find credentials file.  Needs to be located:\n'
                    + gapi_service_creds)
            return
        num_files = len(gsheet_files)
        msg = await self.bot.say('Pulled Google Sheet data 0/{}'.format(num_files))
        for i, k in enumerate(gsheet_files.keys()):
            await self.retrieve_gsheet(k, gc)
            msg = await self.bot.edit_message(msg,
                    'Pulled Google Sheet data {}/{}'.format(i+1, num_files))
        await self.bot.say('Retrieval Complete')

    async def retrieve_gsheet(self, key, gc=None, silent=True):
        if gc is None:
            gc = pygsheets.authorize(service_file=gapi_service_creds, no_cache=True)
        if not silent:
            msg = await self.bot.say('Pulling Google Sheet for {}'.format(key))
        gsdata = GSExport(self.bot, gc, **gsheet_files[key])
        await gsdata.retrieve_data()
        if not silent:
            await self.bot.edit_message(msg, 'Downloaded Google Sheet for {}'.format(key))

    @checks.admin_or_permissions(manage_server=True)
    @commands.command(pass_context=True, aliases=['nbs',], hidden=True)
    async def nerfbuffsell(self, ctx):
        selected = []
        embeds = []
        # em = discord.Embed(color=discord.Color.gold(),title='Nerf, Buff, or Sell')
        # embeds.append(em)
        while len(selected) < 3:
            name_id = random.choice(list(self.champions.values()))
            champ = await self.get_champion(name_id.mattkraftid)
            if champ not in selected:
                if champ.status != 'npc':
                    selected.append(champ)
                    em = discord.Embed(color=champ.class_color, title=champ.full_name)
                    em.set_thumbnail(url=champ.get_avatar())
                    embeds.append(em)
        try:
            messages=[]
            for em in embeds:
                message = await self.bot.say(embed=em)
                await asyncio.sleep(2)
                await self.bot.add_reaction(message=message, emoji=':regional_indicator_n:')
                await self.bot.add_reaction(message=message, emoji=':regional_indicator_b:')
                await self.bot.add_reaction(message=message, emoji=':regional_indicator_s:')
        except:
            await self.bot.say('\n'.join(s.full_name for s in selected))

    @commands.group(pass_context=True, aliases=['champs',])
    async def champ(self, ctx):
        if ctx.invoked_subcommand is None:
            await send_cmd_help(ctx)

    @champ.command(name='featured')
    async def champ_featured(self, champ : ChampConverter):
        '''Champion Featured image'''
        em = discord.Embed(color=champ.class_color, title=champ.full_name)
        em.set_author(name=champ.full_name + ' - ' + champ.short, icon_url=champ.get_avatar())
        em.set_image(url=champ.get_featured())
        await self.bot.say(embed=em)

    @champ.command(name='portrait')
    async def champ_portrait(self, *, champs : ChampConverterMult):
        '''Champion portraits'''
        for champ in champs:
            em = discord.Embed(color=champ.class_color, title=champ.full_name)
            em.set_author(name=champ.full_name + ' - ' + champ.short, icon_url=champ.get_avatar())
            em.set_image(url=champ.get_avatar())
            print(champ.get_avatar())
            await self.bot.say(embed=em)

    @champ.command(name='bio', aliases=('biography',))
    async def champ_bio(self, *, champ : ChampConverterDebug):
        '''Champio Bio'''
        try:
            bio_desc = await champ.get_bio()
        except KeyError:
            await self.say_user_error("Cannot find bio for Champion '{}'".format(champ.full_name))
            return
        em = discord.Embed(color=champ.class_color, title='Champion Biography',
                description=bio_desc)
        em.set_author(name='{0.full_name}'.format(champ), icon_url=champ.get_avatar())
        em.add_field(name='hashtags',
                value=chat.box(' '.join(champ.class_tags.union(champ.tags))),inline=False)
        em.add_field(name='Shortcode', value=champ.short,inline=False)
        em.set_thumbnail(url=champ.get_avatar())
        em.set_footer(text='MCOC Game Files', icon_url='https://imgur.com/UniRf5f.png')
        await self.bot.say(embed=em)

    @champ.command(name='duel')
    async def champ_duel(self, champ : ChampConverter):
        '''Duel & Spar Targets'''
        dataset=data_files['duelist']['local']
        # targets = defaultdict(list)
        targets = []
        # names = {4: 'Duel', 5: 'Sparring'}
        DUEL_SPREADSHEET='https://docs.google.com/spreadsheets/d/1FZdJPB8sayzrXkE3F2z3b1VzFsNDhh-_Ukl10OXRN6Q/view#gid=61189525'
        em = discord.Embed(color=champ.class_color, title='Duel & Spart Targets',url=DUEL_SPREADSHEET)
        em.set_author(name='{0.full_name}'.format(champ), icon_url=champ.get_avatar())
        em.set_thumbnail(url=champ.get_featured())
        em.set_footer(text='2OO2RC51\' Duel Targets',
                icon_url='https://d2jixqqjqj5d23.cloudfront.net/assets/developer/imgs/icons/google-spreadsheet-icon.png')
        target_found = False
        for star in range(3,7):
            for rank in range(1,6):
                key = '{0}-{1}-{2}'.format(star, champ.full_name, rank)
                for data in get_csv_rows(dataset, 'unique', key):#champ.unique):
                    targets.append( '{}{} {} {} : {}'.format(star, champ.star_char, data['maxlevel'], champ.full_name, data['username']))
        if len(targets) > 0:
            em.description='\n'.join(targets)
        else:
            em.description='Target not found!\nAdd one to the Community Spreadhseet!\n[bit.ly/DuelTargetForm](http://bit.ly/DuelTargetForm)'
            em.url='http://bit.ly/DuelTargetForm'
        em.add_field(name='Shortcode', value=champ.short, inline=False)
        await self.bot.say(embed=em)

    @champ.command(name='about', aliases=('about_champ',))
    async def champ_about(self, *, champ : ChampConverterRank):
        '''Champion Base Stats'''
        data = champ.get_spotlight(default='x')
        title = 'Base Attributes for {}'.format(champ.verbose_str)
        em = discord.Embed(color=champ.class_color,
                title='Base Attributes')
        em.set_author(name=champ.verbose_str, icon_url=champ.get_avatar())
        titles = ('Health', 'Attack', 'Crit Rate', 'Crit Dmg', 'Armor', 'Block Prof')
        keys = ('health', 'attack', 'critical', 'critdamage', 'armor', 'blockprof')
        xref = get_csv_row(data_files['crossreference']['local'],'champ',champ.full_name)

        if champ.debug:
            em.add_field(name='Attrs', value='\n'.join(titles))
            em.add_field(name='Values', value='\n'.join([data[k] for k in keys]), inline=True)
            em.add_field(name='Added to PHC', value=xref['4basic'])
        else:
            stats = [[titles[i], data[keys[i]]] for i in range(len(titles))]
            em.add_field(name='Base Stats',
                value=tabulate(stats, width=11, rotate=False, header_sep=False))
        em = await self.get_synergies([champ], em)
        if champ.infopage != 'none':
            em.add_field(name='Infopage',value='<{}>'.format(champ.infopage),inline=False)
        else:
            em.add_field(name='Infopage',value='No spotlight post from Kabam',inline=False)
            em.add_field(name='hashtags',
                    value=chat.box(' '.join(champ.class_tags.union(champ.tags))))
        em.add_field(name='Shortcode', value=champ.short)
        em.set_footer(text='[-SDF-] Spotlight Dataset', icon_url=icon_sdf)
        em.set_thumbnail(url=champ.get_avatar())
        await self.bot.say(embed=em)

    @champ.command(pass_context=True, name='list')
    async def champ_list(self, ctx, *, hargs=''):
        '''List of all champions in prestige order.

        hargs:  [attribute_args] [hashtags]
        The optional attribute arguments can be in any order, with or without spaces.
            <digit>* specifies star <default: 4>
            r<digit> specifies rank <default: 5>
            s<digit> specifies signature level <default: 99>

        Examples:
            /champ list    (all 4* champs rank5, sig99)
            /champ list 5*r3s20 #bleed   (all 5* bleed champs at rank3, sig20)
        '''
        hargs = await hook.HashtagRankConverter(ctx, hargs).convert() #imported from hook
        #await self.update_local()
        roster = hook.ChampionRoster(self.bot, self.bot.user) #imported from hook
        rlist = []
        for champ_class in self.champions.values():
            champ = champ_class(hargs.attrs.copy())
            if champ.has_prestige:
                rlist.append(champ)
        roster.from_list(rlist)
        roster.display_override = 'Prestige Listing: {0.attrs_str}'.format(rlist[0])
        await roster.display(hargs.tags) #imported from hook

    @champ.command(name='released', aliases=('odds','chances',))
    async def champ_released(self, *, champs : ChampConverterMult):
        '''Champion(s) Release Date'''
        for champ in champs:
            xref = get_csv_row(data_files['crossreference']['local'],'champ',champ.full_name)
            em = discord.Embed(color=champ.class_color,
                    title='Release Dates & Est. Pull Chance',url=SPOTLIGHT_DATASET)
            em.set_author(name='{0.full_name}'.format(champ), icon_url=champ.get_avatar())
            em.add_field(name='Feature Crystal', value=xref['released'],inline=False)
            em.add_field(name='4{0.star_char} Basic & \nPremium Hero Crystal'.format(champ), value=xref['4basic'],inline=False)
            em.add_field(name='5{0.star_char} Subfeature'.format(champ), value=xref['5subfeature'],inline=False)
            em.add_field(name='5{0.star_char} Basic'.format(champ), value=xref['5basic'],inline=False)
            state = xref['f/s/b']
            if state == 'b':
                em.add_field(name='Basic 4{0.star_char} Chance'.format(champ), value=xref['4chance'],inline=False)
                em.add_field(name='Basic 5{0.star_char} Chance'.format(champ), value=xref['5chance'],inline=False)
            elif state == 's':
                em.add_field(name='Basic 4{0.star_char} Chance'.format(champ), value=xref['4chance'],inline=False)
                em.add_field(name='Featured 5{0.star_char} Chance'.format(champ), value=xref['5chance'],inline=False)
            elif state == 'f':
                em.add_field(name='Featured 4{0.star_char} Chance'.format(champ), value=xref['4chance'],inline=False)
                em.add_field(name='Featured 5{0.star_char} Chance'.format(champ), value=xref['5chance'],inline=False)
            em.add_field(name='Shortcode', value=champ.short)
            em.set_thumbnail(url=champ.get_featured())
            em.set_footer(text='[-SDF-] Spotlight Dataset', icon_url=icon_sdf)
            await self.bot.say(embed=em)

    @champ.command(pass_context=True, name='sig', aliases=['signature',])
    async def champ_sig(self, ctx, *, champ : ChampConverterSig):
        '''Champion Signature Ability'''
        if champ.star >= 5:
            await self.say_user_error("Sorry.  {0.star}{0.star_char} data for any champion is not currently available".format(champ))
            return
        appinfo = await self.bot.application_info()
        try:
            title, desc, sig_calcs = await champ.process_sig_description(
                    isbotowner=ctx.message.author == appinfo.owner)
        except KeyError:
            await champ.missing_sig_ad()
            raise
            return
        if title is None:
            return
        em = discord.Embed(color=champ.class_color, title='Signature Ability')
        em.set_author(name='{0.full_name}'.format(champ), icon_url=champ.get_avatar())
        em.add_field(name=title, value=champ.star_str)
        em.add_field(name='Signature Level {}'.format(champ.sig),
                value=desc.format(d=sig_calcs))
        em.add_field(name='Shortcode', value=champ.short)
        em.set_footer(text='MCOC Game Files', icon_url='https://imgur.com/UniRf5f.png')
        em.set_thumbnail(url=champ.get_avatar())
        await self.bot.say(embed=em)

    @champ.command(pass_context=True, name='sigplot', hidden=True)
    async def champ_sigplot(self,ctx,*, champ: ChampConverterSig):
        if champ.star <= 4 and champ.star > 1:
            x = 99
        elif champ.star > 4:
            x = 200
        elif champ.star == 1:
            await self.bot.say('1★ champs have no signature ability.')


        try:
            plt.plot([1,2,3,4], [1,4,9,16], 'ro')
            plt.axis([0, 6, 0, 20])
            plt.xlabel('Signature Ability Level')
            plt.ylabel('Signature Ability Effect')
            plt.suptitle('Sig Plot Test')
            # plt.show()
            plt.draw()
            plt.savefig('data/mcoc/sigtemp.png', format='png', dpi=150)
            await self.bot.upload('data/mcoc/sigtemp.png')
        except:
            print('champ_sigplot nothing happened')


    @champ.command(name='stats', aliases=('stat',))
    async def champ_stats(self, *, champs : ChampConverterMult):
        '''Champion(s) Base Stats'''
        for champ in champs:
            data = champ.get_spotlight(default='x')
            embeds =[]
            em = discord.Embed(color=champ.class_color, title='Champion Stats',url=SPOTLIGHT_SURVEY)
            em.set_author(name=champ.verbose_str, icon_url=champ.get_avatar())
            em.set_footer(text='[-SDF-] Spotlight Dataset', icon_url=icon_sdf)
            titles = ('Health', 'Attack', 'Crit Rate', 'Crit Dmg', 'Armor Penetration', 'Block Penetration', 'Crit Resistance', 'Armor', 'Block Prof')
            keys = ('health', 'attack', 'critical', 'critdamage', 'armor_pen', 'block_pen', 'crit_resist', 'armor', 'blockprof')
            xref = get_csv_row(data_files['crossreference']['local'],'champ',champ.full_name)
            # if champ.debug:
            #     em.add_field(name='Attrs', value='\n'.join(titles))
            #     em.add_field(name='Values', value='\n'.join([data[k] for k in keys]), inline=True)
            #     em.add_field(name='Added to PHC', value=xref['4basic'])
            # else:
            stats = [[titles[i], data[keys[i]]] for i in range(len(titles))]
            em.add_field(name='Base Stats', value=tabulate(stats, width=18, rotate=False, header_sep=False), inline=False)
            em.add_field(name='Shortcode',value=champ.short)
            # em.set_thumbnail(url=champ.get_featured())
            embeds.append(em)

            em2 = discord.Embed(color=champ.class_color, title='Champion Stats',url=SPOTLIGHT_SURVEY)
            em2.set_author(name=champ.verbose_str, icon_url=champ.get_avatar())
            em2.set_footer(text='[-SDF-] Spotlight Dataset', icon_url=icon_sdf)
            # em2.set_thumbnail(url=champ.get_featured())
            flats = []
            flats.append(data[keys[0]])
            flats.append(data[keys[1]])
            for k in range(2,len(keys)):
                flats.append('% {}'.format(from_flat(int(data[keys[k]].replace(',','')), int(champ.chlgr_rating))))
            pcts = [[titles[i], flats[i]] for i in range(len(titles))]
            em2.add_field(name='Base Stats %', value=tabulate(pcts, width=19, rotate=False, header_sep=False), inline=False)
            em2.add_field(name='Shortcode', value=champ.short)
            embeds.append(em2)

            try:
                menu = PagesMenu(self.bot, timeout=120, delete_onX=True, add_pageof=True)
                await menu.menu_start(embeds)                # for page in pages:
            except:
                print('PagesMenu failure')
                await self.bot.say(embed=em)

    @champ.command(pass_context=True, name='update', hidden=True)
    async def champ_update(self, ctx, *, args):
        '''Not a real command'''
        msg = '`{0}champ update` does not exist.\n' \
            + '`{0}roster update` is probably what you meant to do'
        prefixes = tuple(self.bot.settings.get_prefixes(ctx.message.server))
        await self.bot.say(msg.format(prefixes[0]))

    @champ.command(name='synergies', aliases=['syn',])
    async def champ_synergies(self, *, champs: ChampConverterMult):
        '''Champion(s) Synergies'''
        if len(champs)==1:
            champ = champs[0]
            em = discord.Embed(color=champ.class_color, title='')
            em.set_author(name=champ.star_name_str, icon_url=champ.get_avatar())
            em.set_thumbnail(url=champ.get_featured())
        else:
            em = discord.Embed(color=discord.Color.red(), title='Champion Synergies')
        em = await self.get_synergies(champs, embed=em)
        em.set_footer(text='CollectorDevTeam', icon_url=COLLECTOR_ICON)
        await self.bot.say(embed=em)

    @staticmethod
    def syn_effect_data(syn_effect, rank):
        rank = syn_effect['rank{}'.format(rank)]
        try:
            effect = [int(v) for v in rank.split(', ')]
        except AttributeError:
            effect = [rank]
        return effect

    async def get_synergies(self, champs, embed=None):
        '''If Debug is sent, data will refresh'''
        if champs[0].debug:
            await self.retrieve_gsheet('synergy', silent=False)
        # sheet = '1Apun0aUcr8HcrGmIODGJYhr-ZXBCE_lAR7EaFg_ZJDY'
        # range_headers = 'Synergies!A1:M1'
        # range_body = 'Synergies!A2:M'
        # foldername = 'synergies'
        # filename = 'synergies'
        # if champs[0].debug:
        #     head_url = GS_BASE.format(sheet,range_headers)
        #     body_url = GS_BASE.format(sheet,range_body)
        #     champ_synergies = await self.gs_to_json(head_url, body_url, foldername, filename)
        #     message = await self.bot.say('Collecting Synergy data ...')
        #     await self.bot.upload(self.shell_json.format(foldername,filename))
        # else:
        #     getfile = self.shell_json.format(foldername, filename)
        #     champ_synergies = dataIO.load_json(getfile)
        #
        # # GS_BASE='https://sheets.googleapis.com/v4/spreadsheets/1Apun0aUcr8HcrGmIODGJYhr-ZXBCE_lAR7EaFg_ZJDY/values/Synergies!A2:L1250?key=AIzaSyBugcjKbOABZEn-tBOxkj0O7j5WGyz80uA&majorDimension=ROWS'
        #
        # range_headers = 'SynergyEffects!A1:G'
        # range_body = 'SynergyEffects!A2:G'
        # filename = 'effects'
        # if champs[0].debug:
        #     head_url = GS_BASE.format(sheet,range_headers)
        #     body_url = GS_BASE.format(sheet,range_body)
        #     synlist = await self.gs_to_json(head_url, body_url, foldername, filename)
        #     await self.bot.edit_message(message, 'Almost done ...')
        #     await self.bot.upload(self.shell_json.format(foldername,filename))
        #     await self.bot.edit_message(message, 'Synergies collected.')
        # else:
        #     getfile = self.shell_json.format(foldername, filename)
        #     synlist = dataIO.load_json(getfile)

        syn_data = dataIO.load_json(local_files['synergy'])
        champ_set = {champ.full_name for champ in champs}
        synergy_package = []
        activated = set()
        # print('len champs: '+str(len(champs)))
        if len(champs) > 1: ## If more than one champ, display synergies triggered
            effectsused = defaultdict(list)
            for champ in champs:
                champ_synergies = syn_data['SynExport'][champ.full_name]
                for lookup, data in champ_synergies.items():
                    if champ.star != data['stars'] or lookup in activated:
                        continue
                    for trigger in data['triggers'].split(','):
                        trigger = trigger.strip()
                        #print(champ.full_name, trigger, lookup)
                        if trigger in champ_set:
                            activated.add(lookup)
                            syneffect = syn_data['SynergyEffects'][data['synergycode']]
                            if syneffect['is_unique'] == 'TRUE' and data['synergycode'] in effectsused:
                                continue
                            effect = self.syn_effect_data(syneffect, data['rank'])
                            effectsused[data['synergycode']].append(effect)

                # for s in synlist: #try this with .keys()
                #     for i in range(1, 4):
                #         lookup = '{}-{}-{}-{}'.format(champ.star, champ.mattkraftid, s, i)
                #         if lookup in champ_synergies:
                #             for c in champs:
                #                 if lookup in activated:
                #                     continue
                #                 elif '[{}]'.format(c.mattkraftid) in champ_synergies[lookup]['mtriggers']:
                #                     effect = [int(v) for v in champ_synergies[lookup]['effect'].split(', ')]
                #                     effectsused[s].append(effect)
                #                     txt = champ_synergies[lookup]['text'].format(*effect)
                #                     activated.add(lookup)
                #                 # synergy_package.append(txt)
            #print(effectsused)
            desc= []
            embed.description = ''.join(c.collectoremoji for c in champs)
            for k, v in effectsused.items():
                syn_effect = syn_data['SynergyEffects'][k]
                array_sum = [sum(row) for row in iter_rows(v, True)]
                txt = syn_effect['text'].format(*array_sum)
                if embed is not None:
                    embed.add_field(name=syn_effect['synergyname'],value=txt,inline=False)
                else:
                    desc.append('{}\n{}\n'.format(syn_effect['synergyname'],txt))
            if embed is None:
                embed='\n'.join(desc)
            return embed
        elif len(champs) == 1: ## If only 1 champ, display synergies available.
            champ = champs[0]
            champ_synergies = syn_data['SynExport'][champ.full_name]
            for lookup, data in champ_synergies.items():
                if champ.star != data['stars']:
                    continue
                syneffect = syn_data['SynergyEffects'][data['synergycode']]
                triggers = data['triggers']
                effect = self.syn_effect_data(syneffect, data['rank'])
                # print(effect)
                try:
                    txt = syneffect['text'].format(*effect)
                except:
                    print(syneffect['text'], effect)
                    raise
                if embed is not None:
                    embed.add_field(name='{}'.format(syneffect['synergyname']), value='+ **{}**\n{}\n'.format(triggers,txt), inline=False)
                synergy_package.append('{}\n{}: {}\n'.format(triggers, syneffect['synergyname'], txt))

            # for champ in champs:
            #     for s in synlist:
            #         for i in range(1, 4):
            #             lookup = '{}-{}-{}-{}'.format(champ.star, champ.mattkraftid, s, i)
            #             if lookup in champ_synergies:
            #                 selected = champ_synergies[lookup]
            #                 triggers = selected['triggers']
            #                 effect = selected['effect'].split(', ')
            #                 # print(effect)
            #                 try:
            #                     txt = champ_synergies[lookup]['text'].format(*effect)
            #                 except:
            #                     print(champ_synergies[lookup]['text'], effect)
            #                     raise
            #                 if embed is not None:
            #                     embed.add_field(name='{}'.format(synlist[s]['synergyname']), value='+ **{}**\n{}\n'.format(triggers,txt), inline=False)
            #                 synergy_package.append('{}\n{}: {}\n'.format(triggers, synlist[s]['synergyname'], txt))
            #if champs[0].debug:
                #await self.bot.delete_message(message)
            if embed is not None:
                return embed
            else:
                desc = '\n'.join(synergy_package)
                return desc

    async def gs_to_json(self, head_url=None, body_url=None, foldername=None, filename=None, groupby_value=None):
        if head_url is not None:
            async with aiohttp.get(head_url) as response:
                try:
                    header_json = await response.json()
                except:
                    print('No header data found.')
                    return
            header_values = header_json['values']

        async with aiohttp.get(body_url) as response:
            try:
                body_json = await response.json()
            except:
                print('No data found.')
                return
        body_values = body_json['values']

        output_dict = {}
        if head_url is not None:
            if groupby_value is None:
                groupby_value = 0
            grouped_by = header_values[0][groupby_value]
            for row in body_values:
                dict_zip = dict(zip(header_values[0],row))
                groupby = row[groupby_value]
                output_dict.update({groupby:dict_zip})
        else:
            output_dict =body_values

        if foldername is not None and filename is not None:
            if not os.path.exists(self.shell_json.format(foldername, filename)):
                if not os.path.exists(self.data_dir.format(foldername)):
                    os.makedirs(self.data_dir.format(foldername))
                dataIO.save_json(self.shell_json.format(foldername, filename), output_dict)
            dataIO.save_json(self.shell_json.format(foldername,filename),output_dict)

            # # Uncomment to debug
            # if champ.debug:
            #     await self.bot.upload(self.shell_json.format(foldername,filename))


        return output_dict

    @commands.command(hidden=True)
    async def dump_sigs(self):
        #await self.update_local()
        sdata = dataIO.load_json(local_files['signature'])
        dump = {}
        for c, champ_class in enumerate(self.champions.values()):
            #if c < 75 or c > 90:
                #continue
            champ = champ_class()
            item = {'name': champ.full_name, 'sig_data': []}
            for i in range(1, 100):
                champ.update_attrs({'sig': i})
                try:
                    title, desc, sig_calcs = await champ.process_sig_description(sdata, quiet=True)
                except (KeyError, IndexError):
                    print("Skipping ", champ.full_name)
                    break
                if sig_calcs is None:
                    break
                if i == 1:
                    item['title'] = title
                    item['description'] = desc
                    item['star_rank'] = champ.star_str
                item['sig_data'].append(sig_calcs)
            if not item['sig_data']:
                continue
            dump[champ.mattkraftid] = item
            print(champ.full_name)
        with open('sig_data_4star.json', encoding='utf-8', mode="w") as fp:
            json.dump(dump, fp, indent='\t', sort_keys=True)
        await self.bot.say('Hopefully dumped')

    @commands.command(hidden=True)
    async def json_sig(self, *, champ : ChampConverterSig):
        if champ.star != 4 or champ.rank != 5:
            await self.bot.say('This function only checks 4* rank5 champs')
            return
        jfile = dataIO.load_json('sig_data_4star.json')
        title, desc, sig_calcs = await champ.process_sig_description(quiet=True)
        jsig = jfile[champ.mattkraftid]
        em = discord.Embed(title='Check for {}'.format(champ.full_name))
        em.add_field(name=jsig['title'],
                value=jsig['description'].format(d=jsig['sig_data'][champ.sig-1]))
        await self.bot.say(embed=em)
        assert title == jsig['title']
        assert desc == jsig['description']
        assert sig_calcs == jsig['sig_data'][champ.sig-1]

    @commands.command(hidden=True)
    async def gs_sig(self):
        await self.update_local()
        gkey = '1kNvLfeWSCim8liXn6t0ksMAy5ArZL5Pzx4hhmLqjukg'
        gc = pygsheets.authorize(service_file=gapi_service_creds, no_cache=True)
        gsdata = GSExport(gc, gkey)
        struct = await gsdata.retrieve_data()
        sigs = load_kabam_json(kabam_bcg_stat_en)
        for key in struct.keys():
            champ_class = self.champions.get(key.lower(), None)
            if champ_class is None:
                continue
            struct[key]['kabam_text'] = champ_class.get_kabam_sig_text(
                    champ_class, sigs=sigs,
                    champ_exceptions=struct['kabam_key_override'])
        with open('data/mcoc/gs_json_test.json', encoding='utf-8', mode='w') as fp:
            json.dump(struct, fp, indent='  ', sort_keys=True)
        await self.bot.upload('data/mcoc/gs_json_test.json')

    @champ.command(name='use', aliases=('howto','htf',))
    async def champ_use(self, *, champs :ChampConverterMult):
        '''How to Fight With videos by MCOC Community'''
        for champ in champs:
            xref = get_csv_row(data_files['crossreference']['local'],'champ',champ.full_name)
            em = discord.Embed(color=champ.class_color, title='How-To-Use: '+champ.full_name, url='https://goo.gl/forms/VXSQ1z40H4Knia0t2')
            await self.bot.say(embed=em)
            if xref['infovideo'] != '':
                await self.bot.say(xref['infovideo'])
            else:
                await self.bot.say('I got nothing. Send the CollectorDevTeam a good video.\nClick the blue text for a survey link.')


    @champ.command(name='info', aliases=('infopage',))
    async def champ_info(self, *, champ : ChampConverterDebug):
        '''Champion Spotlight link'''
        xref = get_csv_row(data_files['crossreference']['local'],'champ',champ.full_name)
        em = discord.Embed(color=champ.class_color, title='Champ Info',url=SPOTLIGHT_SURVEY)
        em.set_author(name='{0.full_name}'.format(champ), icon_url=champ.get_avatar())
        if champ.infopage == 'none':
            em.add_field(name='Kabam Spotlight', value='No URL found')
        else:
            em.add_field(name='Kabam Spotlight', value=champ.infopage)
        if xref['royal_writeup'] != '':
            em.add_field(name='Royal Writeup', value=xref['royal_writeup'])
        em.add_field(name='Shortcode', value=champ.short)
        em.set_footer(text='MCOC Website', icon_url='https://imgur.com/UniRf5f.png')
        em.set_thumbnail(url=champ.get_avatar())
        await self.bot.say(embed=em)

    @champ.command(name='abilities')
    async def champ_abilities(self, *, champ : ChampConverter):
        '''Champion Abilities'''
        xref=get_csv_row(data_files['crossreference']['local'],'champ',champ.full_name)
        abilities=xref['abilities'].split(', ')
        extended_abilities=xref['extended_abilities']

        counters=xref['counters'].split(', ')
        hashtags=xref['hashtags'].split(' #')
        em = discord.Embed(color=champ.class_color, title='Champion Abilities', descritpion='')
        em.description = champ.abilities
        em.set_author(name='{0.full_name}'.format(champ), icon_url=champ.get_avatar())
        if len(extended_abilities) > 1:
            em.add_field(name='Extended Abilities', value=extended_abilities, inline=False)
        if len(counters) > 1:
            em.add_field(name='Counters (#!)', value=', '.join(c.title() for c in counters), inline=False)
        em.add_field(name='Hashtags (#)', value=champ.hashtags, inline=False)
        em.add_field(name='Shortcode', value=champ.short)
        em.add_field(name='Champion Number', value=champ.champNumber)
        em.set_thumbnail(url=champ.get_avatar())
        em.set_footer(text='MCOC Game Files', icon_url='https://imgur.com/UniRf5f.png')
        await self.bot.say(embed=em)

    @champ.command(name='specials', aliases=['special',])
    async def champ_specials(self, champ : ChampConverter):
        '''Special Attack Descritpion'''
        try:
            specials = champ.get_special_attacks()
            em = discord.Embed(color=champ.class_color, title='Champion Special Attacks')
            em.set_author(name='{0.full_name}'.format(champ), icon_url=champ.get_avatar())
            em.add_field(name=specials[0], value=specials[3])
            em.add_field(name=specials[1], value=specials[4])
            em.add_field(name=specials[2], value=specials[5])
            em.set_thumbnail(url=champ.get_avatar())
            em.add_field(name='Shortcode', value=champ.short)
            em.set_footer(text='MCOC Game Files', icon_url='https://imgur.com/UniRf5f.png')
            await self.bot.say(embed=em)
        except:
            await self.bot.say('Special Attack not found')
    # @commands.command()
    # async def sigarray(self, champ : ChampConverter, dbg=1, *args):
    #     '''the Signature Ability of a Champion at multiple levels'''
    #     champ = self._resolve_alias(champ)
    #     title, desc = champ.get_sigarray(**self.settings)
    #     if dbg == 0:
    #         em = discord.Embed(color=champ.class_color, title=title,
    #                 description=desc)
    #     elif dbg == 1:
    #         em = discord.Embed(color=champ.class_color, title=champ.full_name)
    #         em.add_field(name='Signature Ability Array', value=desc)
    #     else:
    #         em = discord.Embed(color=champ.class_color, title=title)
    #         em.add_field(name='__SigLvl__', value='1\n20\n40')
    #         em.add_field(name='__X__', value='1.0\n1.9\n2.1', inline=True)
    #
    #     em.set_thumbnail(url=champ.get_avatar())
    #     await self.bot.say(embed=em)

    @champ.command(name='prestige')
    async def champ_prestige(self, *, champs : ChampConverterMult):
        '''Champion(s) Prestige'''
        pch = [c for c in champs if c.has_prestige]
        numerator = 0
        spch = sorted(pch, key=attrgetter('prestige'), reverse=True)
        if len(spch) < 5:
            denom = len(spch)
        else:
            denom = 5
        print(denom)
        for i in range(0,denom):
            chmp = spch[i]
            print(str(i)+' '+chmp.full_name)
            print(chmp.prestige)
            numerator += int(chmp.prestige)
        print(numerator)
        emtitle='Prestige: {}'.format(numerator/denom)
        em = discord.Embed(color=discord.Color.magenta(), title=emtitle,url=PRESTIGE_SURVEY,
                description='\n'.join([c.verbose_prestige_str for c in
                    sorted(pch, key=attrgetter('prestige'), reverse=True)]))
        em.set_footer(icon_url='https://d2jixqqjqj5d23.cloudfront.net/assets/developer/imgs/icons/google-spreadsheet-icon.png',text='mutamatt Prestige for Collector')
        await self.bot.say(embed=em)

    @champ.command(name='aliases', aliases=('alias',))
    async def champ_aliases(self, *args):
        '''Champion Aliases'''
        em = discord.Embed(color=discord.Color.teal(), title='Champion Aliases')
        champs_matched = set()
        for arg in args:
            if (arg.startswith("'") and arg.endswith("'")) or \
                    (arg.startswith('"') and arg.endswith('"')):
                champs = await self.search_champions(arg[1:-1])
            elif '*' in arg:
                champs = await self.search_champions('.*'.join(re.split(r'\\?\*', arg)))
            else:
                champs = await self.search_champions('.*{}.*'.format(arg))
            for champ in champs:
                if champ.mattkraftid not in champs_matched:
                    em.add_field(name=champ.full_name, value=champ.get_aliases())
                    champs_matched.add(champ.mattkraftid)
        await self.bot.say(embed=em)

    @commands.group(hidden=True, pass_context=True, aliases=['datamine',])
    async def search(self, ctx):
        if ctx.invoked_subcommand is None:
            await send_cmd_help(ctx)

    @search.command(hidden=True, pass_context=True, name='masteries')
    async def search_masteries(self, ctx, term: str = None):
        '''Search for keys or terms within masteries'''
        data =  load_kabam_json(kabam_masteries)
        await self._search_paginate(data, term, None)           # for page in pages:

    @search.command(hidden=True, pass_context=True, name='special_attacks', aliases=['specials'],)
    async def search_special_attacks(self, ctx, term: str = None):
        '''Search for keys or terms within special_attacks'''
        data =  load_kabam_json(kabam_special_attacks)
        await self._search_paginate(data, term, None)           # for page in pages:

    @search.command(hidden=True, pass_context=True, name='bcg_stat_en',aliases=['bcg_stat',])
    async def search_bcg_stat_en(self, ctx, term: str = None):
        '''Search for keys or terms within bcg_stat_en'''
        data =  load_kabam_json(kabam_bcg_stat_en)
        await self._search_paginate(data, term, None)           # for page in pages:
    #
    @search.command(hidden=True, pass_context=True, name='bcg_en', aliases=['bcg',])
    async def search_bcg_en(self, ctx, term: str = None):
        '''Search for keys or terms within bcg_en'''
        data =  load_kabam_json(kabam_bcg_en)
        await self._search_paginate(data, term, None)           # for page in pages:

    async def _search_paginate(self, data, term, v=None):
        keylist = data.keys()
        if term is None:
            print(keylist)
            pages = chat.pagify('\n'.join(k for k in keylist))
            page_list = []
            for page in pages:
                page_list.append(page)
            menu = PagesMenu(self.bot, timeout=120, delete_onX=True, add_pageof=True)
            await menu.menu_start(page_list)                # for page in pages:
        else:
            if term in keylist:
                await self.bot.say(self._bcg_recompile(data[term]))
            else:
                searchlist = []
                for k in keylist:
                    if term in data[k]:
                        searchlist.append('\n{}\n{}\n'.format(k, self._bcg_recompile(data[k])))
                pages = chat.pagify('\n'.join(s for s in searchlist))
                page_list = []
                for page in pages:
                    page_list.append(chat.box(page))
                menu = PagesMenu(self.bot, timeout=120, delete_onX=True, add_pageof=True)
                await menu.menu_start(page_list)


    def _bcg_recompile(self, str_data):
        hex_re = re.compile(r'\[[0-9a-f]{6,8}\](.+?)\[-\]', re.I)
        return hex_re.sub(r'\1', str_data)


    @commands.command(hidden=True)
    async def tst(self, key):
        files = {'bio': (kabam_bio, 'ID_CHARACTER_BIOS_', 'mcocjson'),
                 'sig': (kabam_bcg_stat_en, 'ID_UI_STAT_', 'mcocsig')}
        ignore_champs = ('DRONE', 'SYMBIOD')
        if key not in files:
            await self.bot.say('Accepted Key values:\n\t' + '\n\t'.join(files.keys()))
            return
        data = load_kabam_json(files[key][0])
        no_mcocjson = []
        no_kabam_key = []
        data_keys = {k for k in data.keys() if k.startswith(files[key][1])}
        ignore_keys = set()
        for champ in ignore_champs:
            ignore_keys.update({k for k in data_keys if k.find(champ) != -1})
        data_keys -= ignore_keys
        print(ignore_keys)
        for champ in self.champs:
            if not getattr(champ, files[key][2], None):
                no_mcocjson.append(champ.full_name)
                continue
            kabam_key = files[key][1] + getattr(champ, files[key][2])
            champ_keys = {k for k in data.keys() if k.startswith(kabam_key)}
            if not champ_keys:
                no_kabam_key.append(champ.full_name)
            else:
                data_keys -= champ_keys
        if no_mcocjson:
            await self.bot.say('Could not find mcocjson alias for champs:\n\t' + ', '.join(no_mcocjson))
        if no_kabam_key:
            await self.bot.say('Could not find Kabam key for champs:\n\t' + ', '.join(no_kabam_key))
        if data_keys:
            #print(data_keys, len(data_keys))
            if len(data_keys) > 20:
                dump = {k for k in data_keys if k.endswith('TITLE')}
            else:
                dump = data_keys
            await self.bot.say('Residual keys:\n\t' + '\n\t'.join(dump))
        await self.bot.say('Done')

#My intention was to create a hook command group. If nothing is specified, then drop the URL

    #def _prepare_signature_data(self):
        #raw_data = load_csv(local_files['sig_coeff'])
    @commands.has_any_role('DataDonors','CollectorDevTeam','CollectorSupportTeam','CollectorPartners')
    @commands.group(pass_context=True, aliases=['donate',], hidden=True)
    async def submit(self, ctx):
        if ctx.invoked_subcommand is None:
            await send_cmd_help(ctx)
    # @submit.command(pass_context=True, name='stats')
    # async def submit_stats(self, ctx, args):
    #     # Need to split out hp atk cr cd armor bp
    #     hp = '' #health
    #     atk = '' #attack
    #     cr = '' #crit rate
    #     cd = '' #critical damage
    #     apen = '' #armor penetration
    #     bpen = '' #block penetration
    #     cresist = '' #critical resistance
    #     armor = '' #armor
    #     bp = '' #block proficiency
    #
    #
    #     # _bare_arg = None
    #     # parse_re = re.compile(r'''(?:s(?P<sig>[0-9]{1,3}))|(?:r(?P<rank>[1-5]))|(?:(?P<star>[1-6])\\?\*)|(?:(?P<star>[1-6])\\?\★)|(?:d(?P<debug>[0-9]{1,2}))''', re.X)
    #     parse_re = re.compile(r'''(?:hp(?P<hp>[0-9]{1,6}))
    #                             |(?:atk(?P<atk>[0-9]{1,4}))
    #                             |(?:cr(?P<cr>[0-9]{1,4}))
    #                             |(?:cd(?P<cd>[0-9]{1,4}))
    #                             |(?:armor(?P<armor>[0-9]{1,5}))
    #                             |(?:bp(?P<bp>[0-9]{1,4}))
    #                             ''',re.X)
    #
    #     await self.bot.say('hp: {}\natk: {}\ncr: {}\ncd: {}\narmor: {}\nbp:  {}'.format(hp, atk, cr, cd, armor, bp))

        # async def convert(self):
        #     bot = self.ctx.bot
        #     attrs = {}
        #     if self._bare_arg:
        #         args = self.argument.rsplit(' ', maxsplit=1)
        #         if len(args) > 1 and args[-1].isdecimal():
        #             attrs[self._bare_arg] = int(args[-1])
        #             self.argument = args[0]
        #     arg = ''.join(self.argument.lower().split(' '))
        #     for m in self.parse_re.finditer(arg):
        #         attrs[m.lastgroup] = int(m.group(m.lastgroup))
        #     token = self.parse_re.sub('', arg)
        #     if not token:
        #         err_str = "No Champion remains from arg '{}'".format(self.argument)
        #         await bot.say(err_str)
        #         raise commands.BadArgument(err_str)
        #     return (await self.get_champion(bot, token, attrs))

    @submit.command(pass_context=True, name='prestige')
    async def submit_prestige(self, ctx, champ : ChampConverter, observation : int):
        guild = await self.check_guild(ctx)
        if not guild:
            await self.bot.say('This server is unauthorized.')
            return
        else:
            message = await self.bot.say('Submission registered.\nChampion: {0.verbose_str}\nPrestige: {1}\nPress OK to confirm.'.format(champ, observation))
            await self.bot.add_reaction(message, '❌')
            await self.bot.add_reaction(message, '🆗')
            react = await self.bot.wait_for_reaction(message=message, user=ctx.message.author, timeout=30, emoji=['❌', '🆗'])
            if react is not None:
                if react.reaction.emoji == '❌':
                    await self.bot.say('Submission canceled.')
                elif react.reaction.emoji == '🆗':
                    GKEY = '1HXMN7PseaWSvWpNJ3igUkV_VT-w4_7-tqNY7kSk0xoc'
                    message2 = await self.bot.say('Submission in process.')
                    author = ctx.message.author
                    package = [['{}'.format(champ.mattkraftid), champ.sig, observation, champ.star, champ.rank, champ.max_lvl, author.name, author.id]]
                    check = await self._process_submission(package=package, GKEY=GKEY, sheet='collector_submit')                # await self._process_submit_prestige(ctx, champ, observation)
                    if check:
                        await self.bot.edit_message(message2, 'Submission complete.')
                    else:
                        await self.bot.edit_message(message2, 'Submission failed.')
            else:
                await self.bot.say('Ambiguous response.  Submission canceled')


    @submit.command(pass_context=True, name='duel', aliases=['duels','target'])
    async def submit_duel_target(self, ctx, champ : ChampConverter, observation, pi:int = 0):
        guild = await self.check_guild(ctx)
        if not guild:
            await self.bot.say('This server is unauthorized.')
            return
        else:
            message = await self.bot.say('Duel Target registered.\nChampion: {0.star_name_str}\nTarget: {1}\nPress OK to confirm.'.format(champ, observation))
            await self.bot.add_reaction(message, '❌')
            await self.bot.add_reaction(message, '🆗')
            react = await self.bot.wait_for_reaction(message=message, user=ctx.message.author, timeout=30, emoji=['❌', '🆗'])
            if react is not None:
                if react.reaction.emoji == '❌':
                    await self.bot.say('Submission canceled.')
                elif react.reaction.emoji == '🆗':
                    # GKEY = '1VOqej9o4yLAdMoZwnWbPY-fTFynbDb_Lk8bXDNeonuE'
                    GKEY = '1FZdJPB8sayzrXkE3F2z3b1VzFsNDhh-_Ukl10OXRN6Q'
                    message2 = await self.bot.say('Submission in progress.')
                    author = ctx.message.author
                    star = '{0.star}{0.star_char}'.format(champ)
                    if pi == 0:
                        if champ.has_prestige:
                            pi=champ.prestige
                    now = str(ctx.message.timestamp)
                    package = [[now, author.name, star, champ.full_name, champ.rank, champ.max_lvl, pi, observation, author.id]]
                    print('package built')
                    check = await self._process_submission(package=package, GKEY=GKEY, sheet='collector_submit')
                    if check:
                        await self.bot.edit_message(message2, 'Submission complete.')
                        async with aiohttp.ClientSession() as s:
                            await asyncio.sleep(10)
                            await self.cache_remote_file('duelist', s, force_cache=True, verbose=True)
                            await self.bot.edit_message(message2, 'Submission complete.\nDuel Targets refreshed.')
                    else:
                        await self.bot.edit_message(message2, 'Submission failed.')
            else:
                await self.bot.say('Ambiguous response.  Submission canceled')

    @submit.command(pass_context=True, name='defkill', aliases=['defko',])
    async def submit_awkill(self, ctx, champ : ChampConverter, node:int, ko: int):
        message = await self.bot.say('Defender Kill registered.\nChampion: {0.verbose_str}\nAW Node: {1}\nKills: {2}\nPress OK to confirm.'.format(champ, node, ko))
        await self.bot.add_reaction(message, '❌')
        await self.bot.add_reaction(message, '🆗')
        react = await self.bot.wait_for_reaction(message=message, user=ctx.message.author, timeout=30, emoji=['❌', '🆗'])
        if react is not None:
            if react.reaction.emoji == '❌':
                await self.bot.say('Submission canceled.')
            elif react.reaction.emoji == '🆗':
                GKEY = '1VOqej9o4yLAdMoZwnWbPY-fTFynbDb_Lk8bXDNeonuE' #Collector Submissions
                message2 = await self.bot.say('Submission in progress.')
                author = ctx.message.author
                now = str(ctx.message.timestamp)
                package = [[now, author.name, author.id, champ.unique, node, ko]]
                print('package built')
                check = await self._process_submission(package=package, GKEY=GKEY, sheet='defender_kos')
                if check:
                    await self.bot.edit_message(message2, 'Submission complete.')
                else:
                    await self.bot.edit_message(message2, 'Submission failed.')
        else:
            GKEY = '1VOqej9o4yLAdMoZwnWbPY-fTFynbDb_Lk8bXDNeonuE' #Collector Submissions
            message2 = await self.bot.say('Ambiguous response: Submission in progress.')
            author = ctx.message.author
            now = str(ctx.message.timestamp)
            package = [[now, author.name, author.id, champ.unique, node, ko]]
            print('package built')
            check = await self._process_submission(package=package, GKEY=GKEY, sheet='defender_kos')
            if check:
                await self.bot.edit_message(message2, 'Submission complete.')
            else:
                await self.bot.edit_message(message2, 'Submission failed.')

    @submit.command(pass_context=True, name='100hits')
    async def submit_100hitchallenge(self, ctx, champ : ChampConverter, hits : int, wintersoldier_hp : int, author : discord.User = None):
        if author is None:
            author = ctx.message.author
        message = await self.bot.say('100 Hit Challenge registered.\nChampion: {0.verbose_str}\nHits: {1}\nWinter Soldier HP: {2}\nPress OK to confirm.'.format(champ, hits, wintersoldier_hp))
        await self.bot.add_reaction(message, '❌')
        await self.bot.add_reaction(message, '🆗')
        react = await self.bot.wait_for_reaction(message=message, user=ctx.message.author, timeout=30, emoji=['❌', '🆗'])
        GKEY = '1RoofkyYgFu6XOypoe_IPVHivvToEuLL2Vqv1KDQLGlA' #100 hit challenge
        SHEETKEY = 'collector_submit'
        pct = round(((547774-wintersoldier_hp)/547774)*100, 4)
        package = [[author.name, champ.unique, champ.full_name, champ.star, champ.rank, wintersoldier_hp, hits, pct]]
        print('package built')
        if react is not None:
            if react.reaction.emoji == '❌':
                await self.bot.say('Submission canceled.')
            elif react.reaction.emoji == '🆗':
                message2 = await self.bot.say('Submission in progress.')
                check = await self._process_submission(package=package, GKEY=GKEY, sheet=SHEETKEY)
                if check:
                    await self.bot.edit_message(message2, 'Submission complete.\nWinter Soldier Damage: {}%'.format(pct))
                else:
                    await self.bot.edit_message(message2, 'Submission failed.')
        else:
            message2 = await self.bot.say('Ambiguous response: Submission in progress.')
            print('package built')
            check = await self._process_submission(package=package, GKEY=GKEY, sheet=SHEETKEY)
            if check:
                await self.bot.edit_message(message2, 'Submission complete.\nWinter Soldier Damage: {}%'.format(pct))
            else:
                await self.bot.edit_message(message2, 'Submission failed.')

    async def check_guild(self, ctx):
        authorized = ['215271081517383682','124984400747167744','378035654736609280','260436844515164160']
        serverid = ctx.message.server.id
        if serverid in authorized:
            return True
        else:
            return False

    async def _process_submission(self, package, GKEY, sheet):
        #await self.update_local()
        try:
            gc = pygsheets.authorize(service_file=gapi_service_creds, no_cache=True)
            sh = gc.open_by_key(key=GKEY, returnas='spreadsheet')
            worksheet = sh.worksheet(property='title',value=sheet)
            worksheet.append_table(start='A1',end=None, values=package, dimension='ROWS', overwrite=False)
            worksheet.sync()
            return True
        except FileNotFoundError:
            await self.bot.say('Cannot find credentials file.  Needs to be located:\n'
            + gapi_service_creds)
            return False


    async def _process_submit_prestige(self, ctx, champ, observation):
        GKEY = '1HXMN7PseaWSvWpNJ3igUkV_VT-w4_7-tqNY7kSk0xoc'
        author = ctx.message.author
        level = int(champ.rank)*10
        if champ.star == 5:
            level += 15
        package = [['{}'.format(champ.mattkraftid), champ.sig, observation, champ.star, champ.rank, level, author.name, author.id]]
        #await self.update_local()
        try:
            gc = pygsheets.authorize(service_file=gapi_service_creds, no_cache=True)
        except FileNotFoundError:
            await self.bot.say('Cannot find credentials file.  Needs to be located:\n'
            + gapi_service_creds)
            return
        sh = gc.open_by_key(key=GKEY,returnas='spreadsheet')
        worksheet = sh.worksheet(property='title',value='collector_submit')
        worksheet.append_table(start='A2',end=None, values=package, dimension='ROWS', overwrite=False)
        worksheet.sync()

    @commands.has_any_role('DataDonors','CollectorDevTeam','CollectorSupportTeam','CollectorPartners')
    @commands.group(pass_context=True, hidden=True)
    async def costs(self, ctx):
        guild = await self.check_guild(ctx)
        if not guild:
            await self.bot.say('This server is unauthorized.')
            return
        if ctx.invoked_subcommand is None:
            await send_cmd_help(ctx)

    @costs.command(name='rankup', aliases=['rank',])
    async def cost_rankup(self, ctx, champs : ChampConverterMult):
        counter = 0
        for champ in champs:
            counter += 1
        print('rankup counter: '+str(counter))


def validate_attr(*expected_args):
    def decorator(func):
        def wrapper(self, *args, **kwargs):
            for attr in expected_args:
                if getattr(self, attr + '_data', None) is None:
                    raise AttributeError("{} for Champion ".format(attr.capitalize())
                        + "'{}' has not been initialized.".format(self.champ))
            return func(self, *args, **kwargs)
        return wrapper
    return decorator


class Champion:

    base_tags = {'#cr{}'.format(i) for i in range(10, 130, 10)}
    base_tags.update({'#{}star'.format(i) for i in range(1, 6)})
    base_tags.update({'#awake', }, {'#sig{}'.format(i) for i in range(1, 201)})
    dupe_levels = {2: 1, 3: 8, 4: 20, 5: 20, 6: 20}
    default_stars = {i: {'rank': i+1, 'sig': 99} for i in range(1,5)}
    default_stars[5] = {'rank': 5, 'sig': 200}
    default_stars[6] = {'rank': 1, 'sig': 200}

    def __init__(self, attrs=None):
        if attrs is None:
            attrs = {}
        self.debug = attrs.pop('debug', 0)

        self._star = attrs.pop('star', 4)
        if self._star < 1:
            logger.warn('Star {} for Champ {} is too low.  Setting to 1'.format(
                    self._star, self.full_name))
            self._star = 1
        if self._star > 6:
            logger.warn('Star {} for Champ {} is too high.  Setting to 6'.format(
                    self._star, self.full_name))
            self._star = 6
        self._default = self.default_stars[self._star].copy()

        for k,v in attrs.items():
            if k not in self._default:
                setattr(self, k, v)
        self.tags = set()
        self.update_attrs(attrs)

    def __eq__(self, other):
        return self.immutable_id == other.immutable_id \
                and self.rank == other.rank \
                and self.sig == other.sig

    def update_attrs(self, attrs):
        self.tags.difference_update(self.base_tags)
        for k in ('rank', 'sig'):
            if k in attrs:
                setattr(self, '_' + k, attrs[k])
        if self.sig < 0:
            self._sig = 0
        if self.rank < 1:
            self._rank = 1
        if self.star >= 5:
            if self.rank > 5:
                self._rank = 5
            if self.sig > 200:
                self._sig = 200
        elif self.star < 5:
            if self.rank > (self.star + 1):
                self._rank = self.star + 1
            if self.sig > 99:
                self._sig = 99
        self.tags.add('#cr{}'.format(self.chlgr_rating))
        self.tags.add('#{}star'.format(self.star))
        if self.sig != 0:
            self.tags.add('#awake')
        self.tags.add('#sig{}'.format(self.sig))

    def update_default(self, attrs):
        self._default.update(attrs)

    def inc_dupe(self):
        self.update_attrs({'sig': self.sig + self.dupe_levels[self.star]})

    def get_avatar(self):
        image = '{}images/portraits/portrait_{}.png'.format(remote_data_basepath, self.mcocportrait)
        logger.debug(image)
        return image

    def get_featured(self):
        image = '{}images/featured/GachaChasePrize_256x256_{}.png'.format(
                    remote_data_basepath, self.mcocfeatured)
        logger.debug(image)
        return image

    async def get_bio(self):
        bios = load_kabam_json(kabam_bio)
        key = 'ID_CHARACTER_BIOS_' + self.mcocjson
        if self.debug:
            dbg_str = 'BIO:  ' + key
            await self.bot.say('```{}```'.format(dbg_str))
        if key not in bios:
            raise KeyError('Cannot find Champion {} in data files'.format(self.full_name))
        return bios[key]

    @property
    def star(self):
        return self._star

    @property
    def rank(self):
        return getattr(self, '_rank', self._default['rank'])

    @property
    def sig(self):
        return getattr(self, '_sig', self._default['sig'])

    def is_defined(self, attr):
        return hasattr(self, '_' + attr)

    @property
    def immutable_id(self):
        return (type(self), self.star)

    @property
    def duel_str(self):
        return '{0.star}{0.star_char} {0.rank}/{0.max_lvl} {0.full_name}'.format(self)

    @property
    def star_str(self):
        return '{0.stars_str} {0.rank}/{0.max_lvl}'.format(self)

    @property
    def attrs_str(self):
        return '{0.star}{0.star_char} {0.rank}/{0.max_lvl} sig{0.sig}'.format(self)

    @property
    def unique(self):
        return '{0.star}-{0.mattkraftid}-{0.rank}'.format(self)

    @property
    def coded_str(self):
        return '{0.star}*{0.short}r{0.rank}s{0.sig}'.format(self)

    @property
    def verbose_str(self):
        return '{0.star}{0.star_char} {0.full_name} r{0.rank}'.format(self)
        # return '{0.stars_str} {0.full_name} r{0.rank}'.format(self)

    @property
    def star_name_str(self):
        return '{0.star}{0.star_char} {0.full_name}'.format(self)
        #return '{0.star}★ {0.full_name}'.format(self)

    @property
    def rank_sig_str(self):
        return '{0.rank}/{0.max_lvl} sig{0.sig:<2}'.format(self)

    @property
    def verbose_prestige_str(self):
        return ('{0.class_icon} {0.star}{0.star_char} {0.full_name} '
                + 'r{0.rank} s{0.sig:<2} [ {0.prestige} ]').format(self)

    @property
    def stars_str(self):
        return self.star_char * self.star

    @property
    def star_char(self):
        if self.sig:
            return '★'
        else:
            return '☆'

    @property
    def chlgr_rating(self):
        if self.star == 1:
            return self.rank * 10
        if self.star == 6:
            return (2 * self.star - 2 + self.rank) * 10
        else:
            return (2 * self.star - 3 + self.rank) * 10

    @property
    def max_lvl(self):
        if self.star < 5:
            return self.rank * 10
        else:
            return 15 + self.rank * 10

    @property
    def all_tags(self):
        return self.tags.union(self.class_tags)

    def to_json(self):
        translate = {'sig': 'Awakened', 'hookid': 'Id', 'max_lvl': 'Level',
                    'prestige': 'Pi', 'rank': 'Rank', 'star': 'Stars',
                    'quest_role': 'Role', 'max_prestige': 'maxpi'}
        pack = {}
        for attr, hook_key in translate.items():
            pack[hook_key] = getattr(self, attr, '')
        return pack

    def get_special_attacks(self):
        specials = load_kabam_json(kabam_special_attacks)
        prefix = 'ID_SPECIAL_ATTACK_'
        desc = 'DESCRIPTION_'
        zero = '_0'
        one = '_1'
        two = '_2'
        s0 = specials[prefix + self.mcocjson + zero]
        s1 = specials[prefix + self.mcocjson + one]
        s2 = specials[prefix + self.mcocjson + two]
        s0d = specials[prefix + desc + self.mcocjson + zero]
        s1d = specials[prefix + desc + self.mcocjson + one]
        s2d = specials[prefix + desc + self.mcocjson + two]
        specials = (s0, s1, s2, s0d, s1d, s2d)
        return specials


    @property
    @validate_attr('prestige')
    def prestige(self):
        try:
            if self.prestige_data[self.star][self.rank-1] is None:
                return 0
        except KeyError:
            return 0
        return self.prestige_data[self.star][self.rank-1][self.sig]

    @property
    def has_prestige(self):
        return hasattr(self, 'prestige_data')

    @property
    @validate_attr('prestige')
    def max_prestige(self):
        cur_rank = self.rank
        if self.star == 5:
            rank = 3 if cur_rank < 4 else 4
        else:
            rank = self.star + 1
        self.update_attrs({'rank': rank})
        maxp = self.prestige
        self.update_attrs({'rank': cur_rank})
        return maxp

    @validate_attr('prestige')
    def get_prestige_arr(self, rank, sig_arr, star=4):
        row = ['{}r{}'.format(self.short, rank)]
        for sig in sig_arr:
            try:
                row.append(self.prestige_data[star][rank-1][sig])
            except:
                logger.error(rank, sig, self.prestige_data)
                raise
        return row

    async def missing_sig_ad(self):
        em = discord.Embed(color=self.class_color,
                title='Signature Data is Missing')
        em.add_field(name=self.full_name,
                value='Contribute your data at http://discord.gg/wJqpYGS')
        await self.bot.say(embed=em)

    async def process_sig_description(self, data=None, quiet=False, isbotowner=False):
        if data is None:
            try:
                sd = dataIO.load_json(local_files['signature'])[self.full_name]
            except KeyError:
                sd = self.init_sig_struct()
            except FileNotFoundError:
                if isbotowner:
                    await self.bot.say("**DEPRECIATION WARNING**  "
                            + "Couldn't load json file.  Loading csv files.")
                sd = self.get_sig_data_from_csv()
        else:
            sd = data[self.full_name] if self.full_name in data else data
        brkt_re = re.compile(r'{([0-9])}')
        ktxt = sd['kabam_text']
        if self.debug:
            dbg_str = ['Title:  ' + ktxt['title']['k']]
            dbg_str.append('Simple:  ' + ktxt['simple']['k'])
            dbg_str.append('Description Keys:  ')
            dbg_str.append('  ' + ', '.join(ktxt['desc']['k']))
            dbg_str.append('Description Text:  ')
            dbg_str.extend(['  ' + self._sig_header(d)
                            for d in ktxt['desc']['v']])
            await self.bot.say(chat.box('\n'.join(dbg_str)))

        if not sd['effects'] or not sd['sig_coeff']:
            self.update_attrs(dict(sig=0))
            if not quiet:
                await self.missing_sig_ad()
        if self.sig == 0:
            return ktxt['title']['v'], ktxt['simple']['v'], None

        raw_str = '{:.2f}'
        raw_per_str = '{:.2%}'
        per_str = '{:.2f} ({:.2%})'
        sig_calcs = {}
        ftypes = {}
        #print(json.dumps(sd, indent='  '))
        try:
            stats = sd['spotlight_trunc'][self.unique]
        except (TypeError, KeyError):
            stats = {}
        stats_missing = False
        for i in range(len(sd['effects'])):
            effect = sd['effects'][i]
            ckey = sd['locations'][i]
            m, b = sd['sig_coeff'][i]

            if effect == 'rating':
                sig_calcs[ckey] = raw_str.format(m * self.chlgr_rating + b)
                continue
            per_val = m * log(self.sig) + b
            if effect == 'flat':
                sig_calcs[ckey] = per_str.format(
                        to_flat(per_val, self.chlgr_rating), per_val/100)
            elif effect == 'attack':
                if 'attack' not in stats:
                    stats_missing = True
                    sig_calcs[ckey] = raw_per_str.format(per_val/100)
                    continue
                sig_calcs[ckey] = per_str.format(
                        stats['attack'] * per_val / 100, per_val/100)
            elif effect == 'health':
                if 'health' not in stats:
                    stats_missing = True
                    sig_calcs[ckey] = raw_per_str.format(per_val/100)
                    continue
                sig_calcs[ckey] = per_str.format(
                        stats['health'] * per_val / 100, per_val/100)
            else:
                if per_val.is_integer():
                    sig_calcs[ckey] = '{:.0f}'.format(per_val)
                else:
                    sig_calcs[ckey] = raw_str.format(per_val)

        if stats_missing:
            await self.bot.say(('Missing Attack/Health info for '
                    + '{0.full_name} {0.star_str}').format(self))
        fdesc = []
        for i, txt in enumerate(ktxt['desc']['v']):
            fdesc.append(brkt_re.sub(r'{{d[{0}-\1]}}'.format(i),
                        self._sig_header(txt)))
        if self.debug:
            await self.bot.say(chat.box('\n'.join(fdesc)))
        return ktxt['title']['v'], '\n'.join(fdesc), sig_calcs

    def get_sig_data_from_csv(self):
        struct = self.init_sig_struct()
        coeff = self.get_sig_coeff()
        ekey = self.get_effect_keys()
        spotlight = self.get_spotlight()
        if spotlight and spotlight['attack'] and spotlight['health']:
            stats = {k:int(spotlight[k].replace(',',''))
                        for k in ('attack', 'health')}
        else:
            stats = {}
        struct['spotlight_trunc'] = {self.unique: stats}
        if coeff is None or ekey is None:
            return struct
        for i in map(str, range(6)):
            if not ekey['Location_' + i]:
                break
            struct['effects'].append(ekey['Effect_' + i])
            struct['locations'].append(ekey['Location_' + i])
            try:
                struct['sig_coeff'].append((float(coeff['ability_norm' + i]),
                      float(coeff['offset' + i])))
            except:
                struct['sig_coeff'] = None
        return struct

    def init_sig_struct(self):
        return dict(effects=[], locations=[], sig_coeff=[],
                #spotlight_trunc={self.unique: stats},
                kabam_text=self.get_kabam_sig_text())

    def get_kabam_sig_text(self, sigs=None, champ_exceptions=None):
        if sigs is None:
            sigs = load_kabam_json(kabam_bcg_stat_en)
        if champ_exceptions is None:
            champ_exceptions = {
                #'CYCLOPS_90S': ['ID_UI_STAT_SIGNATURE_CYCLOPS_DESC_90S_AO'],
                'CYCLOPS_90S': ['ID_UI_STAT_SIGNATURE_CYCLOPS_DESC_90S_AO'],
                'LOKI': ['ID_UI_STAT_SIGNATURE_LOKI_LONGDESC'],
                'DEADPOOL': ['ID_UI_STAT_SIGNATURE_DEADPOOL_DESC2_AO'],
                #'ULTRON': ['ID_UI_STAT_SIGNATURE_ULTRON_DESC'],
                #'COMICULTRON': ['ID_UI_STAT_SIGNATURE_ULTRON_DESC'],
                'IRONMAN_SUPERIOR': ['ID_UI_STAT_SIGNATURE_IRONMAN_DESC_AO',
                        'ID_UI_STAT_SIGNATURE_IRONMAN_DESC_B_AO'],
                'BEAST': ['ID_UI_STAT_SIGNATURE_LONGDESC_AO',
                        'ID_UI_STAT_SIGNATURE_LONGDESC_B_AO',
                        'ID_UI_STAT_SIGNATURE_LONGDESC_C_AO',
                        'ID_UI_STAT_SIGNATURE_LONGDESC_D_AO',
                        'ID_UI_STAT_SIGNATURE_LONGDESC_E_AO'],
                'GUILLOTINE': ['ID_UI_STAT_SIGNATURE_GUILLOTINE_DESC'],
                'NEBULA': ['ID_UI_STAT_SIGNATURE_NEBULA_LONG'],
                #'RONAN': ['ID_UI_STAT_SIGNATURE_RONAN_DESC_AO'],
                'MORDO': ['ID_UI_STAT_SIG_MORDO_DESC_AO'],
                'DOC_OCK': ['ID_UI_STAT_ATTRIBUTE_DOC_OCK_SIGNATURE_DESC_A',
                            'ID_UI_STAT_ATTRIBUTE_DOC_OCK_SIGNATURE_DESC_B',
                            'ID_UI_STAT_ATTRIBUTE_DOC_OCK_SIGNATURE_DESC_D',
                            'ID_UI_STAT_ATTRIBUTE_DOC_OCK_SIGNATURE_DESC_C']
            }

        mcocsig = self.mcocsig
        preamble = None
        title = None
        simple = None
        desc = []

        if mcocsig == 'COMICULTRON':
            mcocsig = 'DRONE_TECH'
        elif mcocsig == 'CYCLOPS_90S':
            mcocsig = 'CYCLOPS'

        titles = ('ID_UI_STAT_SIGNATURE_{}_TITLE'.format(mcocsig),
            'ID_UI_STAT_ATTRIBUTE_{}_TITLE'.format(mcocsig),
            'ID_UI_STAT_{}_SIGNATURE_TITLE'.format(mcocsig),
            'ID_UI_STAT_SIG_{}_TITLE'.format(mcocsig),
            'ID_UI_STAT_ATTRIBUTE_{}_SIGNATURE_TITLE'.format(mcocsig),
            'ID_UI_STAT_ATTRIBUTE_{}_SIG_TITLE'.format(mcocsig),
            'ID_UI_STAT_SIGNATURE_FORMAT_{}_SIG_TITLE'.format(mcocsig),
            'ID_UI_STAT_SIGNATURE_{}_SIG_TITLE'.format(mcocsig),
            'ID_STAT_SIGNATURE_{}_TITLE'.format(mcocsig),
            )

        for x in titles:
            if x in sigs:
                title = x

        if title is None:
            raise TitleError("'{}' title not found".format(mcocsig), mcocsig)

        if self.mcocsig == 'COMICULTRON':
            mcocsig = self.mcocsig  # re-init for Ultron Classic

        preambles = ('ID_UI_STAT_SIGNATURE_{}'.format(mcocsig),
            'ID_UI_STAT_{}_SIGNATURE'.format(mcocsig),
            'ID_UI_STAT_SIG_{}'.format(mcocsig),
            'ID_UI_STAT_ATTRIBUTE_{}_SIGNATURE'.format(mcocsig),
            'ID_UI_STAT_SIGNATURE_FORMAT_{}_SIG'.format(mcocsig),
            'ID_UI_STAT_SIGNATURE_{}_SIG'.format(mcocsig),
            'ID_STAT_SIGNATURE_{}'.format(mcocsig)
            )

        for x in preambles:
            if x + '_SIMPLE' in sigs:
                preamble = x
                break

        # if preamble is 'undefined':
        #     raise KeyError('DEBUG - Preamble not found')
        if preamble + '_SIMPLE_NEW2' in sigs:
            simple = preamble + '_SIMPLE_NEW2'
        if preamble + '_SIMPLE_NEW' in sigs:
            simple = preamble + '_SIMPLE_NEW'
        elif preamble + '_SIMPLE' in sigs:
            simple = preamble + '_SIMPLE'
        else:
            raise KeyError('Signature SIMPLE cannot be found with: {}_SIMPLE'.format(preamble))


        if self.mcocsig == 'CYCLOPS_90S':
            desc.append('ID_UI_STAT_SIGNATURE_CYCLOPS_DESC_90S_AO')
        elif mcocsig in champ_exceptions:
            desc.extend(champ_exceptions[mcocsig])
        elif preamble + '_DESC_NEW' in sigs:
            desclist = ('_DESC_NEW','_DESC_NEW_B')
            if preamble + '_DESC_NEW2' in sigs:
                desclist = ('_DESC_NEW2','_DESC_NEW2_B')
            elif preamble + '_DESC_NEW_FIXED' in sigs:
                desclist = ('_DESC_NEW_FIXED','_DESC_NEW_B_FIXED')
            for k in desclist:
                if preamble + k in sigs:
                    if preamble + k + '_AO' in sigs:
                        desc.append(preamble + k + '_AO')
                    else:
                        desc.append(preamble + k)
        elif preamble + '_5STAR_DESC_MOD' in sigs:
            desc.append(preamble+'_DESC_MOD')
        else:
            for k in ('_DESC','_DESC_A','_DESC_B','_DESC_C','_DESC_D','_LONG','_LONG_2'):
                if preamble + k + '_UPDATED' in sigs:
                    k = k + '_UPDATED'
                if preamble + k in sigs:
                    if preamble + k + '_ALT' in sigs:
                        desc.append(preamble + k + '_ALT')
                    elif preamble + k + '_AO' in sigs:
                        desc.append(preamble + k + '_AO')
                    else:
                        desc.append(preamble + k)
        return dict(title={'k': title, 'v': sigs[title]},
                    simple={'k': simple, 'v': sigs[simple]},
                    desc={'k': desc, 'v': [sigs[k] for k in desc]})

    def get_sig_coeff(self):
        return get_csv_row(local_files['sig_coeff'], 'CHAMP', self.full_name)

    def get_effect_keys(self):
        return get_csv_row(local_files['effect_keys'], 'CHAMP', self.full_name)

    def get_spotlight(self, default=None):
        return get_csv_row(data_files['spotlight']['local'], 'unique',
                self.unique, default=default)

    def get_aliases(self):
        return '```{}```'.format(', '.join(self.alias_set))

    @staticmethod
    def _sig_header(str_data):
        hex_re = re.compile(r'\[[0-9a-f]{6,8}\](.+?)\[-\]', re.I)
        return '• ' + hex_re.sub(r'**\1**', str_data)

class PagesMenu:

    EmojiReact = namedtuple('EmojiReact', 'emoji include page_inc')

    def __init__(self, bot, *, add_pageof=True, timeout=30, choice=False,
            delete_onX=True):
        self.bot = bot
        self.timeout = timeout
        self.add_pageof = add_pageof
        self.choice = choice
        self.delete_onX = delete_onX
        self.embedded = True

    async def menu_start(self, pages):
        page_list = []
        if isinstance(pages, list):
            page_list = pages
        else:
            for page in pages:
                page_list.append(page)
        page_length = len(page_list)
        self.embedded = isinstance(page_list[0], discord.Embed)
        self.all_emojis = OrderedDict([(i.emoji, i) for i in (
            self.EmojiReact("\N{BLACK LEFT-POINTING DOUBLE TRIANGLE}", page_length > 5, -5),
            self.EmojiReact("\N{BLACK LEFT-POINTING TRIANGLE}", True, -1),
            self.EmojiReact("\N{CROSS MARK}", True, None),
            self.EmojiReact("\N{BLACK RIGHT-POINTING TRIANGLE}", True, 1),
            self.EmojiReact("\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE}", page_length > 5, 5),
                      )])

        print('menu_pages is embedded: '+str(embedded))

        if self.add_pageof:
            for i, page in enumerate(page_list):
                if isinstance(page, discord.embed):
                    ftr = page.footer
                    page.set_footer(text='{} (Page {} of {})'.format(ftr.text,
                            i+1, page_length), icon_url=ftr.icon_url)
                else:
                    page += '\n(Page {} of {})'.format(i+1, page_length)

        self.page_list = page_list
        await self.display_page(None, 0)

    async def display_page(self, message, page):
        if not message:
            if isinstance(page, discord.Embed) == True:
                message = await self.bot.say(embed=self.page_list[page])
            else:
                message = await self.bot.say(self.page_list[page])
            self.included_emojis = set()
            for emoji in self.all_emojis.values():
                if emoji.include:
                    await self.bot.add_reaction(message, emoji.emoji)
                    self.included_emojis.add(emoji.emoji)
        else:
            if self.embedded == True:
                message = await self.bot.edit_message(message, embed=self.page_list[page])
            else:
                message = await self.bot.edit_message(message, self.page_list[page])
        await asyncio.sleep(1)

        react = await self.bot.wait_for_reaction(message=message,
                timeout=self.timeout, emoji=self.included_emojis)
        if react is None:
            try:
                await self.bot.clear_reactions(message)
            except discord.Forbidden:
                logger.warn("clear_reactions didn't work")
                for emoji in self.included_emojis:
                    await self.bot.remove_reaction(message, emoji, self.bot.user)
            return None

        emoji = react.reaction.emoji
        pages_to_inc = self.all_emojis[emoji].page_inc if emoji in self.all_emojis else None
        if pages_to_inc:
            next_page = (page + pages_to_inc) % len(self.page_list)
            try:
                await self.bot.remove_reaction(message, emoji, react.user)
                await self.display_page(message=message, page=next_page)
            except discord.Forbidden:
                await self.bot.delete_message(message)
                await self.display_page(message=None, page=next_page)
        elif emoji == '\N{CROSS MARK}':
            try:
                if self.delete_onX:
                    await self.bot.delete_message(message)
                else:
                    await self.bot.clear_reactions(message)
            except discord.Forbidden:
                await self.bot.say("Bot does not have the proper Permissions")

def bound_lvl(siglvl, max_lvl=99):
    if isinstance(siglvl, list):
        ret = []
        for j in siglvl:
            if j > max_lvl:
                j = max_lvl
            elif j < 0:
                j = 0
            ret.append(j)
    else:
        ret = siglvl
        if siglvl > max_lvl:
            ret = max_lvl
        elif siglvl < 0:
            ret = 0
    return ret

def tabulate(table_data, width, rotate=True, header_sep=True, align_out=True):
    rows = []
    cells_in_row = None
    for i in iter_rows(table_data, rotate):
        if cells_in_row is None:
            cells_in_row = len(i)
        elif cells_in_row != len(i):
            raise IndexError("Array is not uniform")
        if align_out:
            fstr = '{:<{width}}'
            if len(i) > 1:
                fstr += '|' + '|'.join(['{:>{width}}']*(len(i)-1))
            rows.append(fstr.format(*i, width=width))
        else:
            rows.append('|'.join(['{:^{width}}']*len(i)).format(*i, width=width))
    if header_sep:
        rows.insert(1, '|'.join(['-' * width] * cells_in_row))
    return chat.box('\n'.join(rows))

def iter_rows(array, rotate):
    if not rotate:
        for i in array:
            yield i
    else:
        for j in range(len(array[0])):
            row = []
            for i in range(len(array)):
                row.append(array[i][j])
            yield row

def load_kabam_json(file):
    raw_data = dataIO.load_json(file)
    data = {}
    for d in raw_data['strings']:
        data[d['k']] = d['v']
    return data

def _truncate_text(self, text, max_length):
    if len(text) > max_length:
        if text.strip('$').isdigit():
            text = int(text.strip('$'))
            return "${:.2E}".format(text)
        return text[:max_length-3] + "..."
    return text

def get_csv_row(filecsv, column, match_val, default=None):
    logger.debug(match_val)
    csvfile = load_csv(filecsv)
    for row in csvfile:
        if row[column] == match_val:
            if default is not None:
                for k, v in row.items():
                    if v == '':
                        row[k] = default
            return row

def get_csv_rows(filecsv, column, match_val, default=None):
    logger.debug(match_val)
    csvfile = load_csv(filecsv)
    package =[]
    for row in csvfile:
        if row[column] == match_val:
            if default is not None:
                for k, v in row.items():
                    if v == '':
                        row[k] = default
            package.append(row)
    return package

def load_csv(filename):
    return csv.DictReader(open(filename))

def padd_it(word,max : int,opt='back'):
    loop = max-len(str(word))
    if loop > 0:
        padd = ''
        for i in loop:
            padd+=' '
        if opt =='back':
            return word+padd
        else:
            return padd+word
    else:
        logger.warn('Padding would be negative.')

# avoiding cyclic importing
from . import hook as hook

def setup(bot):
    if not hasattr(bot, '_command_error_orig'):
        bot._command_error_orig = bot.on_command_error
        @bot.event
        async def on_command_error(error, ctx):
            if isinstance(error, QuietUserError):
                bot.logger.info('<{}> {}'.format(type(error).__name__, error))
            else:
                await bot._command_error_orig(error, ctx)
    bot.add_cog(MCOC(bot))
