import asyncio
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
    if len(reservations) == 0:
        return None
    assert len(reservations) == 1

    instances = reservations[0]["Instances"]
    assert len(instances) == 1

    return instances[0]


class MyClient(discord.Client):
    def __init__(self, *, intents, **options):
        super().__init__(intents=intents, **options)

        self.commands_channel_name = "server-commands"
        self.write_dynamic_ip_tasks = {}

    async def on_ready(self):
        print("Logged on as", self.user)

    @staticmethod
    async def write_dynamic_ip(instance_name, channel):
        for i in range(10):
            await asyncio.sleep(1)

            instance = describe_instance(instance_name)
            if instance is None:
                return

            network_interfaces = instance["NetworkInterfaces"]
            if len(network_interfaces) != 1:
                return

            network_interface = network_interfaces[0]
            if "Association" not in network_interface:
                continue

            association = network_interface["Association"]
            if "PublicIp" not in association:
                continue

            stable = False
            if "IpOwnerId" in association and association["IpOwnerId"] != "amazon":
                stable = True

            if not stable:
                await channel.send(f"IP for {instance_name}: \n```{association['PublicIp']}```")
            return

    async def on_message(self, message):
        if message.author == self.user:
            return
        if not message.content.startswith("!"):
            return

        channel = message.channel
        if not channel.category:
            return
        if channel.name != self.commands_channel_name:
            return

        instance_name = channel.category.name

        command = message.content[1:]

        if command == "start":
            instance = describe_instance(instance_name)
            if instance is None:
                await message.channel.send(f"Instance not found: {instance_name}")
                return

            await message.channel.send(f"Starting {instance_name}...")

            state = instance["State"]["Name"]

            if state != "stopped":
                await message.channel.send(f"Cannot start instance. Instance state: {state}")
                return

            instance_id = instance["InstanceId"]
            try:
                ec2.start_instances(InstanceIds=[instance_id], DryRun=False)
            except ClientError as e:
                await message.channel.send(
                    f"Failed to start instance:\n"
                    f"```\n"
                    f"{str(e)}\n"
                    f"```"
                )
                return

            await message.channel.send(f"Started {instance_name}.")

            self.write_dynamic_ip_tasks[instance_name] = asyncio.create_task(
                self.write_dynamic_ip(instance_name, message.channel)
            )

        elif command == "ip":
            instance = describe_instance(instance_name)
            if instance is None:
                await message.channel.send(f"Instance not found: {instance_name}.")
                return

            network_interfaces = instance["NetworkInterfaces"]
            if len(network_interfaces) != 1:
                await message.channel.send(f"Unable to get IP address for {instance_name}")
                return

            network_interface = network_interfaces[0]
            if "Association" not in network_interface:
                await message.channel.send(f"Unable to get IP address for {instance_name}. Is the server online?")
                return

            association = network_interface["Association"]
            if "PublicIp" not in association:
                await message.channel.send(f"Unable to get IP address for {instance_name}")
                return

            stable = False
            if "IpOwnerId" in association and association["IpOwnerId"] != "amazon":
                stable = True
            stability = "stable IP" if stable else "dynamic IP"

            await message.channel.send(f"IP for {instance_name} ({stability}): \n```{association['PublicIp']}```")


intents = discord.Intents.all()
client = MyClient(intents=intents)
client.run(config["discord_token"])
