import json
import discord
import boto3
from botocore.exceptions import ClientError

config = json.load(open("config.json"))

ec2 = boto3.client(
    "ec2",
    aws_access_key_id=config["aws_access_key_id"],
    aws_secret_access_key=config["aws_secret_access_key"]
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

        self.instance_name = config["watcher_instance_name"]

    async def on_ready(self):
        print("Logged on as", self.user)

    async def on_message(self, message):
        if message.author == self.user:
            return
        if not message.content.startswith("!"):
            return

        command = message.content[1:]

        if command == "stop":
            await message.channel.send(f"Stopping {self.instance_name}...")

            instance = describe_instance(self.instance_name)
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

            await message.channel.send(f"Stopped {self.instance_name}.")

        if command == "start":
            await message.channel.send(f"Starting {self.instance_name}...")

            instance = describe_instance(self.instance_name)
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

            await message.channel.send(f"Started {self.instance_name}.")


intents = discord.Intents.all()
client = MyClient(intents=intents)
client.run(config["discord_token"])
