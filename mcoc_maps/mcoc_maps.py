import discord
from discord.ext import commands

class mcoc_maps:
    aq_map = {'aq5':{'map': 'aq5', 'maptitle':'5'},
        'aq5.1':{'map': 'aq51','maptitle':'5 Tier 1'},
        'aq5.2':{'map':  'aq52', 'maptitle':'5 Tier 2'},
        'aq5.3':{'map': 'aq53','maptitle':'5 Tier 3'},}

    warmaps = {'af','ag','ag+','ah','ai','bf','bg','bg+','bh','bi','cf','cg',
                'cg+','ch','ci','df','dg','dg+','dh','ef','eg','eg+','eh','ei'}
    basepath = 'https://raw.githubusercontent.com/JasonJW/mcoc-cogs/master/mcoc_maps/data/maps/'
    icon_sdf = 'https://raw.githubusercontent.com/JasonJW/mcoc-cogs/master/mcoc/data/icon_sdf.png'

    def __init__(self, bot):
        self.bot = bot

    @commands.command(pass_context=True, aliases=['warmap','aqmap'])
    async def mmap(self, ctx, *, args):
        '''Select a Map
        aq maps : aq5, aq5.1, aq5.2, aq5.3
            /map aq5
        war map syntax: /map <left><right>
             <left> = [a, b, c, d, e]
             <right> = [f, g, g+, h, i]'''

        if len(args)==0:
            message = 'Select a Map\naq maps : aq5, aq5.1, aq5.2, aq5.3\n/map aq5\nwar map syntax: /map <left><right>\n<left> = [a, b, c, d, e]\n<right> = [f, g, g+, h, i]'
            await self.bot.say(message)
        else:
            args = str(args).split(' ')
            for maptype in args:
                if maptype in self.aq_map:
                    mapurl = '{}{}.png'.format(self.basepath, self.aq_map[maptype]['map'])
                    maptitle = 'Alliance Quest {}'.format(self.aq_map[maptype]['maptitle'])
                    em = discord.Embed(color=discord.Color.gold(),title=maptitle)
                    em.set_image(url=mapurl)
                elif maptype in self.warmaps:
                    mapurl = '{}{}.png'.format(self.basepath, self.maptype.lower())
                    mapTitle = 'Alliance War Map {}'.format(self.maptype.upper())
                    em = discord.Embed(color=discord.Color.gold(),title=mapTitle)
                    em.set_image(url=mapurl)
                else:
                    em=discord.Embed(color=discord.Color.gold(),title='Apologies',desc='Summoner, I cannot find a suitable map.')
                    em.set_footer(text='Presented by [-SDF-]',icon_url=self.icon_sdf)
                await self.bot.say(embed=em)

def setup(bot):
    bot.add_cog(mcoc_maps(bot))
