# bot.py
import datetime
import json
import math
import os
import random
import re

import discord
import tabulate
from discord.ext import commands
from dotenv import load_dotenv

intents = discord.Intents.default()
intents.members = True

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

with open('cards.json') as cards:
    CARD_LIST = json.load(cards)

command_prefix = os.getenv('COMMAND_PREFIX', '!')
bot = commands.Bot(command_prefix=command_prefix, intents=intents)

group_regex = re.compile('Runner Group (\\d+): (.+)')
defenders_regex = re.compile('Defenders: (.+)')
alert_regex = re.compile('Alerts: (.*) \\(\\+\\d+\\)')
active_group_regex = re.compile('Defending facility from group (\\d+)')


class Group:

    def __init__(self, group_num: int = 1, runners=None):
        if runners is None:
            runners = []
        self.group_num = group_num
        self.runners = runners

    def add_runner(self, runner: str):
        self.runners.append(runner)

    def __str__(self):
        runners = ', '.join([f'`{x}`' for x in self.runners])

        return f'Runner Group {self.group_num}: {runners}'


class ProtectionCard:

    def __init__(self, card_id, card_name, boost):
        self.card_id = card_id
        self.card_name = card_name
        self.boost = boost


class RunStatus:

    def __init__(self, groups=None, alerts: int = 0, current_depth: int = -1, defenders=None, protection_cards=None,
                 active_group=None):
        if groups is None:
            groups = [Group()]
        if protection_cards is None:
            protection_cards = []
        if defenders is None:
            defenders = []
        self.groups = groups
        self.alerts = alerts
        self.current_depth = current_depth
        self.protection_cards = protection_cards
        self.defenders = defenders
        self.active_group = active_group
        self.active_group_obj = None

    def __str__(self):
        defenders = ', '.join([f'`{x}`' for x in self.defenders])

        defenders = f"\nDefenders: {defenders}" if defenders else ''

        alert_bonus = self.bonus_from_alerts(self.alerts)

        self.groups.sort(key=lambda x: x.group_num)

        groups = '\n'.join([str(x) for x in list(filter(lambda group: group.runners, self.groups))])

        protection_cards = []

        for i, card in enumerate(self.protection_cards):
            prefix = ' -> ' if i == self.current_depth else ''
            protection_cards.append(
                [prefix, card.card_id, card.card_name, card.boost]
            )

        if protection_cards:
            formatted_cards = '```\n{}\n```'.format(
                tabulate.tabulate(protection_cards, ["", "Card ID", "Card name", "Boost"], tablefmt="github")
            )
        else:
            formatted_cards = ''

        active_group = f"\nDefending facility from group {self.active_group}" if self.active_group else ''

        return "`!!! Run status !!!`\n{}{}{}\nAlerts: {} (+{})\n{}".format(
            groups,
            defenders,
            active_group,
            self.alerts,
            alert_bonus,
            formatted_cards
        )

    @staticmethod
    def bonus_from_alerts(alerts):
        return math.floor(-0.5 + math.sqrt(0.5 * 0.5 - (4 * 0.5 * (0 - alerts))))

    @classmethod
    def from_message(cls, message: discord.Message):
        groups = []
        defenders = []
        alerts = 0
        current_depth = -1
        protection_cards = []
        active_group = None

        for line in message.content.split('\n'):
            if line == '`!!! Run status !!!`':
                continue

            match = group_regex.match(line)

            if match:
                group_num = int(match.group(1))
                runners = [x.strip('` ') for x in match.group(2).split(',')]
                groups.append(Group(group_num, runners))
                continue

            match = defenders_regex.match(line)

            if match:
                defenders = [x.strip('`') for x in match.group(1).split(', ')]
                continue

            match = alert_regex.match(line)

            if match:
                alerts = int(match.group(1))
                continue

            match = active_group_regex.match(line)

            if match:
                active_group = int(match.group(1))

            if line == '```':
                break

        # Find the table
        split = message.content.split('```')

        if len(split) > 1:
            table = split[1]
            rows = table.split("\n")

            for i, row in enumerate(rows[3:-1]):
                cols = row.split('|')
                card_id = cols[2].strip()
                card_name = cols[3].strip()
                card_boost = int(cols[4].strip())

                if cols[1].strip() == '->':
                    current_depth = i

                protection_cards.append(ProtectionCard(card_id, card_name, card_boost))

        return RunStatus(
            groups=groups,
            alerts=alerts,
            current_depth=current_depth,
            defenders=defenders,
            protection_cards=protection_cards,
            active_group=active_group
        )

    def remove_from_group(self, nickname):
        for group in self.groups:
            if nickname in group.runners:
                group.runners.remove(nickname)
                return

        if nickname in self.defenders:
            self.defenders.remove(nickname)

    def add_to_group(self, group_num, nick):
        for group in self.groups:
            if group.group_num == group_num:
                group.add_runner(nick)
                return

        self.groups.append(Group(group_num, [nick]))

    def alerts_from_active_group(self):
        active_group = self.get_active_group()

        num_runners = len(active_group.runners)

        mapping = {
            0: 0,
            1: 0,
            2: 1,
            3: 2,
            4: 4,
            5: 7,
            6: 11
        }

        if num_runners in mapping:
            return num_runners, mapping[num_runners]

        return num_runners, ((num_runners * (num_runners + 1)) / 2) - 10

    def get_active_group(self):
        if self.active_group_obj is None or self.active_group_obj.group_num != self.active_group:
            group_num = self.active_group

            for group in self.groups:
                if group.group_num == group_num:
                    self.active_group_obj = group
                    return group

            raise ValueError('Couldn\'t find group with number {}'.format(group_num))

        return self.active_group_obj

    def add_card(self, card_id):
        card_name = CARD_LIST[card_id]
        self.protection_cards.append(ProtectionCard(card_id=card_id, card_name=card_name, boost=0))

    def get_active_card(self):
        if self.current_depth < 0 or self.current_depth >= len(self.protection_cards):
            raise ValueError(f'Unknown active card - do you need to run {command_prefix}next-card?')

        return self.protection_cards[self.current_depth]


@bot.event
async def on_ready():
    print(f'{bot.user.name} has connected to Discord!')


control_role_name = 'Control' if os.getenv('UPPERCASE_CONTROL') else 'control'


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.errors.CheckFailure):
        await ctx.send('You do not have the correct role for this command.')
    elif isinstance(error, commands.errors.MissingRequiredArgument):
        await ctx.send(error)
    elif isinstance(error, commands.errors.CommandNotFound):
        await ctx.send("Unknown command - try {0}help to see the available commands".format(command_prefix))
        pass
    elif isinstance(error, discord.ext.commands.errors.BadArgument):
        await ctx.reply(error.args[0])
    else:
        control = discord.utils.get(ctx.guild.roles, name='bot-master')

        await ctx.send(f'{control.mention} there was a problem running this command please investigate')
        raise error


@bot.command(
    name='run-facility',
)
async def create_run(ctx, short_corp: str, facility: str):
    guild: discord.Guild = ctx.guild

    if short_corp not in CORPORATION_NAMES:
        await ctx.send(
            '{0} - {1} not found (must be one of {2})'.format(
                ctx.message.author.mention,
                short_corp,
                ', '.join(CORPORATION_NAMES)
            )
        )
        return

    category_name = f'runs-{short_corp}'
    category: discord.CategoryChannel = discord.utils.get(guild.categories, name=category_name)
    if not category:
        category = await guild.create_category(category_name)

    text_channel: discord.TextChannel = discord.utils.get(category.text_channels,
                                                          name=f'{short_corp}-{facility.lower()}')

    if not text_channel:
        await ctx.send(
            '{0} - {1} not found as a facility for {2}'.format(
                ctx.message.author.mention,
                facility,
                CORPORATION_NAMES[short_corp]
            )
        )
        return

    # Make sure the runner isn't already on a run - that'd be naughty!
    for role in ctx.author.roles:
        if role.name.find('run-') == 0:
            await ctx.send(
                f'{ctx.message.author.mention} - you are already on a run!'
            )
            return

    voice_channel: discord.VoiceChannel = discord.utils.get(category.voice_channels,
                                                            name=f'{short_corp}-{facility.lower()}')

    role = None

    # Check if there's a run role already - if not we'll create a new one
    for key in text_channel.overwrites:
        if isinstance(key, discord.Role) and key.name.find('run-') == 0:
            role = key
            break

    send_initiation_message = False

    if not role:
        # Work out what's the new run number
        while True:
            random_bytes = random.getrandbits(16)

            role_name = f"run-{random_bytes}"
            # Next, create the run-* role
            role = discord.utils.get(guild.roles, name=role_name)

            if not role:
                role = await guild.create_role(name=role_name)
                send_initiation_message = True
                break

    await text_channel.set_permissions(role, read_messages=True)
    await voice_channel.set_permissions(role, view_channel=True)

    corp_role: discord.Role = discord.utils.get(guild.roles, name=CORPORATION_ROLE_NAMES[short_corp])

    if send_initiation_message:

        status = RunStatus()

        status.add_to_group(1, ctx.message.author.nick)

        message = await text_channel.send(str(status))

        await message.pin()

        await text_channel.send(
            "!!! RUN INITIATED !!!\n" +
            f"{corp_role.mention} please send your security representative to defend\n" +
            f"Once all runners have arrived and settled, start defending with `{command_prefix}start-run <group>`"
        )

        await text_channel.send(
            f"When resolving rolls, use the `{command_prefix}roll` command.\n" +
            f"To roll 6 d8 and count the number of success, use `{command_prefix}roll 6d8`.\n" +
            f"To roll 6 d6 and count the number of successes, use `{command_prefix}roll 6d6`\n" +
            f"You can play cards using the `{command_prefix}play` command" +
            f" - see your relevant Google doc for the command you need"
        )
    else:
        message = await pinned_message_from_channel(text_channel)

        status = RunStatus.from_message(message)

        status.add_to_group(1, ctx.message.author.nick)

        await message.edit(content=status)

    await ctx.message.author.add_roles(role)

    await text_channel.send(
        f'{ctx.message.author.mention} has joined the run. ' +
        f'If you are defending, run `{command_prefix}defend`. ' +
        f'If there are multiple groups, run `{command_prefix}group <number>` to join the right group'
    )


@bot.command(name='defend', help='Switch to defending a run instead of attacking')
async def defend(ctx: commands.context.Context):
    try:
        message = await pinned_message_from_context(ctx)
    except ValueError as error:
        await ctx.send(
            '{} - {}'.format(
                ctx.author.mention,
                error.args[0]
            )
        )
        return

    status = RunStatus.from_message(message)

    nickname = ctx.author.nick

    status.defenders.append(nickname)
    status.remove_from_group(nickname)

    await message.edit(content=status)

    await ctx.send('Moved {} to defender'.format(ctx.author.mention))


@bot.command(name='group', help='Switch to a different runner group')
async def join_group(ctx: commands.context.Context, group_num: int):
    try:
        message = await pinned_message_from_context(ctx)
    except ValueError as error:
        await ctx.send(
            '{} - {}'.format(
                ctx.author.mention,
                error.args[0]
            )
        )
        return

    status = RunStatus.from_message(message)

    nickname = ctx.author.nick

    status.remove_from_group(nickname)
    status.add_to_group(group_num, nickname)

    await message.edit(content=status)

    await ctx.send('Moved {} to group {}'.format(ctx.author.mention, group_num))


async def pinned_message_from_context(ctx):
    return await pinned_message_from_channel(ctx.channel)


async def pinned_message_from_channel(channel: discord.TextChannel):
    pins = await channel.pins()
    if not pins:
        raise ValueError('No pinned message found, did you run this in a run channel?')
    message: discord.Message = pins[0]
    return message


@bot.command(name='run-status', help='Redisplay the run status')
async def run_status(ctx: commands.context.Context):
    try:
        message = await pinned_message_from_context(ctx)
    except ValueError as error:
        await ctx.send(
            '{} - {}'.format(
                ctx.author.mention,
                error.args[0]
            )
        )
        return

    await ctx.send(content=str(RunStatus.from_message(message)))


@bot.command(name='defend-facility', help='Defend a facility against a group of runners (defaults to group 1)')
async def start_run(ctx: commands.context.Context, group_num=1):
    try:
        message = await pinned_message_from_context(ctx)
    except ValueError as error:
        await ctx.send(
            '{} - {}'.format(
                ctx.author.mention,
                error.args[0]
            )
        )
        return

    status = RunStatus.from_message(message)
    status.current_depth = -1

    await ctx.send(f'Beginning defence against group {group_num}...')

    status.active_group = group_num
    num_runners, alerts = status.alerts_from_active_group()

    await ctx.send(f'{num_runners} runners in group, triggering {alerts} alerts')
    status.alerts = alerts

    active_group = status.get_active_group()

    channel_members = await ctx.guild.fetch_members().flatten()

    for runner in active_group.runners:
        member: discord.Member = discord.utils.get(channel_members, nick=runner)

        if member:
            await ctx.send(
                '{} - you are on this run. If you are tagged, run `{}alerts <number-of-tags>`'.format(
                    member.mention,
                    command_prefix
                )
            )

    await ctx.send(
        "{} - run started. Once the runners have added their alerts from tags, begin by running `{}next-card <card-id>`".format(
            ctx.author.mention,
            command_prefix
        )
    )

    await message.edit(content=status)


@bot.command(name='alerts', help='Adds alerts to the active run')
async def add_alerts(ctx: commands.context.Context, num_alerts: int):
    try:
        message = await pinned_message_from_context(ctx)
    except ValueError as error:
        await ctx.send(
            '{} - {}'.format(
                ctx.author.mention,
                error.args[0]
            )
        )
        return

    status = RunStatus.from_message(message)
    status.alerts += num_alerts

    await ctx.send(
        "Added {} alerts (new total is {})".format(
            num_alerts,
            status.alerts
        )
    )

    await message.edit(content=status)


@bot.command(name='next-card', help='Plays the next card in the facility')
async def next_card(ctx: commands.context.Context, card=None):
    try:
        message = await pinned_message_from_context(ctx)
    except ValueError as error:
        await ctx.send(
            '{} - {}'.format(
                ctx.author.mention,
                error.args[0]
            )
        )
        return

    status = RunStatus.from_message(message)
    status.current_depth += 1

    if card is None:
        # Get the next card from the status
        if status.current_depth < 0 or status.current_depth >= len(status.protection_cards):
            await ctx.send(
                '{} - Haven\'t seen a card for this level yet - play `{}next-card <card-id>`'.format(
                    ctx.author.mention,
                    command_prefix
                )
            )
            return

        card = status.protection_cards[status.current_depth].card_id
        await play_card(ctx, card)
    else:
        add = False
        if status.current_depth < len(status.protection_cards):
            next_card = status.protection_cards[status.current_depth].card_id

            if next_card != card:
                await ctx.send(
                    f'Already have a card for this level, using {next_card} instead of {card}'
                )

            card = next_card
        else:
            add = True

        if not await play_card(ctx, card):
            return

        if add:
            status.add_card(card)

    await message.edit(content=status)

    await ctx.send(
        f'Facing card {status.current_depth + 1}\n'
        f'Security may boost this card using `{command_prefix}boost <amount>`\n'
        f'To calculate bonus strength, use `{command_prefix}calculate-strength`\n'
        f'If alerts are triggered, use `{command_prefix}alerts <num-alerts>` to add to the calculation\n'
        f'Once this card has been resolved, use `{command_prefix}next-card <card-id>` to move to the next card'
    )


@bot.command(name='previous-card', help='Goes back one card in the facility')
async def previous_card(ctx: commands.context.Context):
    try:
        message = await pinned_message_from_context(ctx)
    except ValueError as error:
        await ctx.send(
            '{} - {}'.format(
                ctx.author.mention,
                error.args[0]
            )
        )
        return

    status = RunStatus.from_message(message)
    status.current_depth -= 1

    # Get the next card from the status
    if status.current_depth < 0 or status.current_depth >= len(status.protection_cards):
        await ctx.send(
            '{} - No previous card. Did you mean to use `{}next-card` instead?'.format(
                ctx.author.mention,
                command_prefix
            )
        )
        return

    card = status.protection_cards[status.current_depth].card_id
    await play_card(ctx, card)

    await message.edit(content=status)

    await ctx.send(
        f'Facing card {status.current_depth + 1}\n'
        f'Security may boost this card using `{command_prefix}boost <amount>`\n'
        f'To calculate bonus strength, use `{command_prefix}calculate-strength`\n'
        f'If alerts are triggered, use `{command_prefix}alerts <num-alerts>` to add to the calculation\n'
        f'Once this card has been resolved, use `{command_prefix}next-card <card-id>` to move to the next card'
    )


@bot.command(name='boost', help='Boost the currently active card')
async def boost(ctx: commands.context.Context, amount: int):
    try:
        message = await pinned_message_from_context(ctx)
    except ValueError as error:
        await ctx.send(
            '{} - {}'.format(
                ctx.author.mention,
                error.args[0]
            )
        )
        return

    status = RunStatus.from_message(message)

    active_card: ProtectionCard

    try:
        active_card = status.get_active_card()
    except ValueError as error:
        await ctx.send(
            '{} - {}'.format(
                ctx.author.mention,
                error.args[0]
            )
        )
        return

    active_card.boost += amount

    await message.edit(content=status)

    amount_to_pay = sum(range(active_card.boost - amount + 1, active_card.boost + 1))

    await ctx.send(
        f'Boosted `{active_card.card_name}` by {amount} (new amount is {active_card.boost})\n'
        f'Don\'t forget pay the cost for it (you should pay `{amount_to_pay}`)'
    )


@bot.command(name='calculate-strength', help='Calculate the strength of the currently active card')
async def boost(ctx: commands.context.Context):
    try:
        message = await pinned_message_from_context(ctx)
    except ValueError as error:
        await ctx.send(
            '{} - {}'.format(
                ctx.author.mention,
                error.args[0]
            )
        )
        return

    status = RunStatus.from_message(message)

    active_card: ProtectionCard

    try:
        active_card = status.get_active_card()
    except ValueError as error:
        await ctx.send(
            '{} - {}'.format(
                ctx.author.mention,
                error.args[0]
            )
        )
        return

    bonus_from_alerts = status.bonus_from_alerts(status.alerts)
    bonus_from_boost = active_card.boost
    bonus_from_depth = math.floor(status.current_depth / 2)

    table = tabulate.tabulate(
        [
            ['Alerts', status.alerts, bonus_from_alerts],
            ['Boost', active_card.boost, bonus_from_boost],
            ['Depth', status.current_depth + 1, bonus_from_depth],
        ],
        [
            'Section', 'Amount', 'Bonus'
        ],
        tablefmt="github"
    )

    total_bonus = bonus_from_boost + bonus_from_alerts + bonus_from_depth
    await ctx.send(
        f'```\n{table}\n```Total bonus dice: {total_bonus}'
    )


@bot.command(name='clear-runs', help='Deletes *all* run channels and roles for end of turn clean up')
@commands.has_role(control_role_name)
async def clear_runs(ctx):
    guild = ctx.guild

    # Get all channels in this category
    for corp_name in CORPORATION_NAMES:
        category_name = f'runs-{corp_name}'
        category = discord.utils.get(guild.categories, name=category_name)

        if category:
            channels = category.text_channels
            await ctx.send(f'Deleting content in {len(channels)} channels, please wait...')

            channel: discord.TextChannel
            delta = datetime.timedelta(days=14)
            for channel in channels:
                msgs = await channel.history(limit=100, after=datetime.datetime.now() - delta).flatten()
                if not msgs:
                    continue

                try:
                    await ctx.send(f'Deleting content in {channel.name}')
                    await channel.delete_messages(msgs)
                except discord.DiscordException:
                    continue

    from discord import Role
    role: Role
    for role in guild.roles:
        if role.name.find('run-') == 0:
            await role.delete()

    await ctx.send(f'Runs cleared')
    await guild.fetch_roles()


@bot.command(name='play', help='Plays the card with the given name')
async def play_card(ctx: commands.context.Context, card: str):
    if card not in CARD_LIST:
        await ctx.send(f'{ctx.message.author.mention} Unknown card {card}')
        return False
    else:
        card_name = CARD_LIST[card]
        file = discord.File(f'card-images/{card}.png', filename=f'{card_name}.png')
        await ctx.send(f'{ctx.message.author.nick or ctx.message.author.name} plays {card_name}', file=file)
        return True


async def create_category(guild, name, overwrites=None, text_channels=None, voice_channels=None):
    if voice_channels is None:
        voice_channels = {}
    if text_channels is None:
        text_channels = {}
    if overwrites is None:
        overwrites = {}
    category = discord.utils.get(guild.categories, name=name)

    if not category:
        category = await guild.create_category(
            name=name,
            overwrites=overwrites
        )

    for name in text_channels:
        await guild.create_text_channel(
            name=name,
            category=category,
            overwrites=text_channels[name]
        )

    for name in voice_channels:
        await guild.create_voice_channel(
            name=name,
            category=category,
            overwrites=text_channels[name]
        )

    return category


async def delete_category(category):
    category_channels = category.channels
    for channel in category_channels:
        await channel.delete()

    await category.delete()


CORPORATION_NAMES = {
    'augmented': 'Augmented Nucleotech',
    'dtc': 'Digital Tactical Control',
    'genetic': 'Genetic Equity',
    'gordon': 'Gordon Corporation',
    'mccullough': 'McCullough Mechanical'
}

CORPORATION_ROLE_NAMES = {
    'augmented': os.getenv('ANT_ROLE_NAME', 'augmented-nucleotech'),
    'dtc': os.getenv('DTC_ROLE_NAME', 'digital-tactical-control'),
    'genetic': os.getenv('GENEQ_ROLE_NAME', 'genetic-equity'),
    'gordon': os.getenv('GORDON_ROLE_NAME', 'gordon-corporation'),
    'mccullough': os.getenv('MCM_ROLE_NAME', 'mccullough-mechanical')
}


@bot.command(name='starting-facilities', help='Builds all the starting facilities')
@commands.has_role(control_role_name)
async def build_starting_facilities(ctx: commands.context.Context):
    starting_facilities = {
        'augmented': [
            ('Corporate', 'SameignlegurA'),
            ('Research', 'RannsóknirA'),
            ('Security', 'MátturA'),
            ('Power', 'OrkaA'),
        ],
        'dtc': [
            ('Arms', 'ArmsA'),
            ('Corporate', 'CorporateA'),
            ('Research', 'ResearchA'),
            ('Security', 'SecurityA'),
            ('Security', 'SecurityB'),
        ],
        'genetic': [
            ('Corporate', 'CorporateA'),
            ('Research', 'ResearchA'),
            ('Research', 'ResearchB'),
            ('Research', 'ResearchC'),
            ('Security', 'SecurityA'),
        ],
        'gordon': [
            ('Corporate', 'CorporateA'),
            ('Corporate', 'CorporateB'),
            ('Corporate', 'CorporateC'),
            ('Research', 'ResearchA'),
            ('Security', 'SecurityA'),
        ],
        'mccullough': [
            ('Corporate', 'CorporateA'),
            ('Factory', 'FactoryA'),
            ('Research', 'ResearchA'),
            ('Research', 'ResearchB'),
            ('Security', 'SecurityA'),
        ]
    }

    guild = ctx.guild

    channel: discord.TextChannel = discord.utils.get(guild.channels, name='facility-list')

    delta = datetime.timedelta(days=100)
    await ctx.send('Clearing up old facilities...')
    while True:
        msgs = await channel.history(limit=100, after=datetime.datetime.now() - delta).flatten()
        if not msgs:
            break

        try:
            await channel.delete_messages(msgs)
        except discord.DiscordException:
            continue

    for short_corp in starting_facilities:
        await ctx.send(f'Doing {CORPORATION_NAMES[short_corp]}')
        corp_facilities = starting_facilities[short_corp]

        category_name = f'runs-{short_corp}'
        category = discord.utils.get(guild.categories, name=category_name)

        if category:
            await delete_category(category)
            await guild.fetch_channels()

        for (facility_type, facility_name) in corp_facilities:
            await raw_build_facility(ctx, short_corp, facility_type, facility_name)

    await ctx.reply('Done! *phew*')


async def raw_build_facility(ctx: commands.context.Context, short_corp: str, facility_type: str, facility_name: str):
    if short_corp not in CORPORATION_NAMES:
        raise ValueError(
            '{0} not found (must be one of {1})'.format(
                short_corp,
                ', '.join(CORPORATION_NAMES)
            )
        )

    guild = ctx.guild

    from discord import TextChannel
    channel: TextChannel = discord.utils.get(guild.channels, name='facility-list')

    assert channel is not None, "facility-list was not found?"

    corporation_name = CORPORATION_NAMES[short_corp]

    facilities = []
    message_to_edit: discord.message = None

    async for message in channel.history():
        if corporation_name in message.content:
            facilities = await facility_from_message(message)
            message_to_edit = message
            break

    # Make sure the names are unique
    if facility_name in [x[0] for x in facilities]:
        raise ValueError('Already have a facility with that name')

    facilities.append([facility_name, facility_type])

    table_string = tabulate.tabulate(facilities, ["Facility name", "Facility Type"], tablefmt="github")
    message_contents = f'{corporation_name} facilities:\n```\n{table_string}\n```'

    if message_to_edit:
        await message_to_edit.edit(content=message_contents)
    else:
        await channel.send(message_contents)

    # Now create a run channel
    channel_name = f'{short_corp}-{facility_name.lower()}'
    control = discord.utils.get(guild.roles, name=control_role_name)

    role = discord.utils.get(guild.roles, name=CORPORATION_ROLE_NAMES[short_corp])
    category_name = f'runs-{short_corp}'
    category = discord.utils.get(guild.categories, name=category_name)

    if not category:
        category = await guild.create_category(category_name)

    await guild.create_text_channel(
        name=channel_name,
        category=category,
        overwrites={
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            control: discord.PermissionOverwrite(read_messages=True),
            role: discord.PermissionOverwrite(read_messages=True)
        }
    )

    await guild.create_voice_channel(
        name=channel_name,
        category=category,
        overwrites={
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            control: discord.PermissionOverwrite(view_channel=True),
            role: discord.PermissionOverwrite(view_channel=True)
        }
    )


@bot.command(name='build-facility', help='Builds a facility')
@commands.has_role(control_role_name)
async def build_facility(ctx: commands.context.Context, short_corp: str, facility_type: str, facility_name: str):
    try:
        await raw_build_facility(ctx, short_corp, facility_type, facility_name)
        await ctx.reply(f'facility built')
    except ValueError as error:
        await ctx.reply(error.args[0])


@bot.command(name='remove-facility', help='Remove a facility')
@commands.has_role(control_role_name)
async def remove_facility(ctx: commands.context.Context, short_corp: str, facility_name: str):
    from discord import TextChannel
    from tabulate import tabulate

    guild: discord.Guild = ctx.guild

    channel: TextChannel = discord.utils.get(guild.channels, name='facility-list')

    assert channel is not None, "facility-list was not found?"

    corporation_name = CORPORATION_NAMES[short_corp]

    async for message in channel.history():
        if corporation_name in message.content:
            facilities = await facility_from_message(message)
            facilities = list(filter(lambda x: x[0] != facility_name, facilities))

            table_string = tabulate(facilities, ["Facility name", "Facility Type"], tablefmt="github")
            message_contents = f'{corporation_name} facilities:\n```\n{table_string}\n```'

            await channel.send(message_contents)
            await message.delete()

            channel = discord.utils.get(guild.channels, name=f'{short_corp}-{facility_name.lower()}')

            while channel:
                await channel.delete()
                await guild.fetch_channels()
                channel = discord.utils.get(guild.channels, name=f'{short_corp}-{facility_name.lower()}')

            await ctx.send(f'{ctx.message.author.mention} - facility removed')

            break


async def facility_from_message(message):
    return [[y.strip() for y in x.split('|')[1:-1]] for x in message.content.split("\n")[4:-1]]


@bot.command(name='roll', help='Rolls dice')
async def roll_dice(ctx: commands.context.Context, die_string: str):
    try:
        (amount, die_type) = die_string.lower().split('d')
        amount = int(amount)
        die_type = int(die_type)
    except ValueError:
        await ctx.send(f'{ctx.message.author.mention} dice format unknown - use `1d6`, `5d8` etc')
        return

    values = [random.randint(1, die_type) for _ in range(amount)]
    values.sort(reverse=True)
    values = [f"**{x}**" if x >= 5 else str(x) for x in values]
    success = list(filter(lambda x: x[0] == '*', values))

    result = f'{len(success)} successes\nRolls: {", ".join(values)}'

    await ctx.send(f'{ctx.message.author.mention} rolls `{die_string}`: {result}')


bot.run(TOKEN)
