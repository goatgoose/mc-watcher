import json
import discord
import boto3
from botocore.exceptions import ClientError

config = json.load(open("config.json"))

ec2 = boto3.client(
    "ec2",
    aws_access_key_id=config["aws_access_key_id"],
    aws_secret_access_key=config["aws_secret_access_key"],
    region_name=config["aws_region"]
)


def describe_instance(name_tag):
    response = ec2.describe_instances(
        Filters=[{
            "Name": "tag:Name",
            "Values": [name_tag]
        }]
    )

    reservations = response["Reservations"]
    assert len(reservations) == 1

    instances = reservations[0]["Instances"]
    assert len(instances) == 1

    return instances[0]


class MyClient(discord.Client):
    def __init__(self, *, intents, **options):
        super().__init__(intents=intents, **options)

        self.instance_names = config["instance_names"]
        self.commands_channel_name = "server-commands"

    async def on_ready(self):
        print("Logged on as", self.user)

        await self.create_channels()

    async def create_channels(self):
        for guild in self.guilds:
            for instance_name in self.instance_names:
                category = discord.utils.get(guild.categories, name=instance_name)
                if not category:
                    print(f"Creating {instance_name} category")
                    await guild.create_category(instance_name)

                category = discord.utils.get(guild.categories, name=instance_name)
                assert category is not None

                channel = discord.utils.get(category.text_channels, name=self.commands_channel_name)
                if not channel:
                    await category.create_text_channel(self.commands_channel_name)

    async def on_message(self, message):
        if message.author == self.user:
            return
        if not message.content.startswith("!"):
            return

        channel = message.channel
        if not channel.category:
            return

        instance_name = channel.category.name
        if instance_name not in self.instance_names:
            await message.channel.send(f"Instance not found: {instance_name}")
            return

        command = message.content[1:]

        if command == "stop":
            await message.channel.send(f"Stopping {instance_name}...")

            instance = describe_instance(instance_name)
            state = instance["State"]["Name"]

            if state != "running":
                await message.channel.send(f"Cannot stop instance. Instance state: {state}")
                return

            instance_id = instance["InstanceId"]
            try:
                ec2.stop_instances(InstanceIds=[instance_id], DryRun=False)
            except ClientError as e:
                await message.channel.send("Failed to stop instance.")
                print(e)
                return

            await message.channel.send(f"Stopped {instance_name}.")

        if command == "start":
            await message.channel.send(f"Starting {instance_name}...")

            instance = describe_instance(instance_name)
            state = instance["State"]["Name"]

            if state != "stopped":
                await message.channel.send(f"Cannot start instance. Instance state: {state}")
                return

            instance_id = instance["InstanceId"]
            try:
                ec2.start_instances(InstanceIds=[instance_id], DryRun=False)
            except ClientError as e:
                await message.channel.send("Failed to start instance.")
                print(e)
                return

            await message.channel.send(f"Started {instance_name}.")


intents = discord.Intents.all()
client = MyClient(intents=intents)
client.run(config["discord_token"])
