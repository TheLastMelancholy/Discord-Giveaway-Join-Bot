#!/usr/bin/python3
import requests, configparser, asyncio, aiohttp, tqdm, itertools
from collections import namedtuple
import random

limit = 100  # Number of messages to scan in the channel. MAX: 100
baseurl = "https://discord.com/api/v8/"
UserConfig = namedtuple('UserConfig', 'token wait_time username')
connection_lock = asyncio.Lock()



async def get_server_ids(session, auth_token):
    async with connection_lock:
        while True:
            try:
                async with session.get(
                    f"{baseurl}/users/@me/guilds",
                    headers={"Authorization": auth_token},
                ) as response:
                    response = await response.json()
                server_ids = []
                for server in response:
                    #print("*"*10)
                    print(server)
                    server_ids.append(server["id"])
                return server_ids
            except Exception as e:
                print(f"Error getting server id's. Retrying.")


async def get_channel_ids(session, auth_token, server_id):
    async with connection_lock:
        async with session.get(
            f"{baseurl}/guilds/{server_id}/channels",
            headers={"Authorization": auth_token},
        ) as response:
            response = await response.json()

        channel_ids = []
        for channel in response:
            if channel["type"] == 0 or channel["type"] == 4 or channel["type"] == 5:
                channel_ids.append(channel["id"])
        return channel_ids


async def get_messages(session, auth_token, channel_id):
    async with connection_lock:
        while True:
            async with session.get(
                f"{baseurl}/channels/{channel_id}/messages?limit={limit}",
                headers={"Authorization": auth_token},
            ) as response:
                response = response
                headers = response.headers
                messages = await response.json()
            if "Retry-After" in headers:
                await asyncio.sleep(5)
                continue
            else:
                break
        return {"messages": messages, "channel_id": channel_id}


def evaluate_message(message):
    if "bot" in message["author"] and "reactions" in message:
        for reaction in message["reactions"]:
            if reaction["emoji"]["name"] == "🎉" and reaction["me"] == False:
                return True

    return False


async def react_messages(session, auth_token, channel_id, message_id):
    async with connection_lock:
        while True:
            async with session.put(
                f"{baseurl}/channels/{channel_id}/messages/{message_id}/reactions/🎉/@me",
                headers={"Authorization": auth_token},
            ) as response:
                headers = response.headers

            if "Retry-After" in headers:
                await asyncio.sleep(10)
                continue
            else:
                break
        return


async def main(user_configuration):
    auth_token, pooling_wait_time, user_name       =  user_configuration

    recent_messages_id_s = []

    iterations_count = 0
    async with aiohttp.ClientSession() as session:  # create aiohttp session
        ### GET server IDs
        print(f"[{user_name}] Fetching servers...")
        tasks = [get_server_ids(session, auth_token)]
        for t in tqdm.tqdm(asyncio.as_completed(tasks), total=len(tasks)):
            server_ids = await t

        ### GET channel IDs
        print(f"[{user_name}] Fetching channels...")
        tasks = [
            get_channel_ids(session, auth_token, server_id) for server_id in server_ids
        ]
        channel_ids = []
        for t in tqdm.tqdm(asyncio.as_completed(tasks), total=len(tasks)):
            channel_ids.append(await t)
        channel_ids = list(itertools.chain.from_iterable(channel_ids))


        while True:

        ### GET messages
            print(f"[{user_name}] Fetching messages...")
            tasks = [
                get_messages(session, auth_token, channel_id) for channel_id in channel_ids
            ]
            channels = []

            for t in tqdm.tqdm(asyncio.as_completed(tasks), total=len(tasks)):
                channels.append(await t)

            giveaways = []
            new_messages_count = 0
            all_messages_count = 0


            for channel in channels:
                all_messages_count += len(channel["messages"])

                for message in channel["messages"]:

                    if not message or not type(message) == dict:
                        continue

                    if message['channel_id'] + ":" + message['id'] not in recent_messages_id_s:
                        #print(recent_messages_id_s)
                        recent_messages_id_s.append(message['channel_id'] + ":" + message['id'])
                        #print(message['channel_id'] + ":" + message['id'])
                        new_messages_count +=1
                    else:
                        continue


                    if  evaluate_message(message) == True:
                        giveaways.append(
                            {"messages": message, "channel_id": channel["channel_id"]}
                        )


            if not all_messages_count:
                print(f"[{user_name}] no messages extracted at all. Sleep for 2x timeout of {pooling_wait_time*2}s to ensure script not being banned.")
                await asyncio.sleep(pooling_wait_time*2)
                continue

            if not new_messages_count:
                print(f"[{user_name}] no new mesages. Nothing to process. Sleep for 2x timeout of {pooling_wait_time*2}s to avoid working idle")
                await asyncio.sleep(pooling_wait_time*2)
                continue


            #extracted_msgs_num = len(channel["messages"])
            print(f"[{user_name}] --------------------------")
            print(f"[{user_name}] {len(giveaways)} giveaways found! of {new_messages_count} new messages from {all_messages_count} last messages.")
            print(f"[{user_name}] --------------------------")

            ### React to giveaways
            print(f"[{user_name}] Joining...")
            giveaway_ids = []
            for item in giveaways:
                giveaway_ids.append(
                    {
                        "message_id": item["messages"]["id"],
                        "channel_id": item["channel_id"],
                    }
                )

            tasks = [
                react_messages(
                    session,
                    auth_token,
                    giveaway_id["channel_id"],
                    giveaway_id["message_id"],
                )
                for giveaway_id in giveaway_ids
            ]

            responses = []
            for t in tqdm.tqdm(asyncio.as_completed(tasks), total=len(tasks)):
                responses.append(await t)

            if len(recent_messages_id_s) > int(limit*1.5):
                recent_messages_id_s = recent_messages_id_s[len(recent_messages_id_s)-int(limit*1.5):]

            print(f"[{user_name}] Waiting for {pooling_wait_time}s")
            await asyncio.sleep(pooling_wait_time)



###############################
##### PARSING UTILITIES #######
###############################



def validate_token(user_data):
    auth_token = user_data.token
    with requests.get(
        baseurl + "/users/@me", headers={"Authorization": auth_token}
    ) as response:
        response = response

        if response.status_code == 200:
            user = response.json()["username"]
            print("----------------------")
            print(f"Token {auth_token[:5]}... is valid for user " + user)
            print("----------------------")
            return user


        elif response.status_code == 401:
            print(response)
            print(f"{auth_token[:5]}... of {user_data.username} is not a valid token!")
            print()

        elif response.status_code == 429:
            retry_after = response.headers["Retry-After"]
            exit(
                f"Too many requests! \nPlease retry again in {retry_after} seconds ({round(int(retry_after) / 60)} minute(s)).\nAlternatively, change your IP."
            )
        else:
            print(f"Unknown error for {auth_token[:5]}... ! The server returned {response}.")


def extract_recorded_users_data():

    config = configparser.ConfigParser()
    config.read("config.ini")

    default_wait_interval = 5

    #print(config)

    for user_name in config:
        #print(user_name)
        if "token" in config[user_name]:
            if "wait_time" not in config[user_name]:
                print(f"Wait time imterval are not specified for user {user_name}. Using default value of {default_wait_interval}s.")
            yield UserConfig(config[user_name]["token"], int(config[user_name]["wait_time"]) if "wait_time" in config[user_name] else default_wait_interval, user_name)



def update_config_file(name, user_data):
    parser = configparser.ConfigParser()
    parser.read("config.ini")
    if name in parser:
        print(f"Updating existing user record for {name}")
    else:
        print(f"Adding new record for {name}")

    parser[name] = {"token": user_data.token,"wait_time": user_data.wait_time}


    with open('config.ini', 'w') as configfile:
        parser.write(configfile)



def prepare_tokens():

    valid_tokens = list(filter(validate_token, extract_recorded_users_data()))
    user_defined_tokens = []


    if not valid_tokens:
        print("There are no valid user configurations in config.ini file\nPlease add user data in format\n\n[USER_NAME]\ntoken = authentification token\nwait_time = time interval to wait between requests.\n\n* And verify that any of user tokens are valid\n")

        while input("\nWould you like to input new user token now?\ny/n ").lower() == "y":
            user_defined = UserConfig(input(
            "Input authentification token here: "
            ).strip(),
            int(input("Input wait interval here: ")), "new_user")

            user_name = validate_token(user_defined)

            if user_name:
                user_verified = UserConfig(user_defined.token, user_defined.wait_time, user_name)
                user_defined_tokens.append(user_verified)
                update_config_file(user_name, user_verified)
            else:
                print("Specified token are not valid")

    tokens_to_process = valid_tokens+user_defined_tokens

    return tokens_to_process





def init():

    valid_user_configurations = prepare_tokens()

    if not valid_user_configurations:
        exit("There is no valid users specified. Both from .ini file and user input. Nothing to do there are.")


    for conf in valid_user_configurations:
        asyncio.get_event_loop().create_task(main(conf))
    asyncio.get_event_loop().run_forever()



import warnings

if __name__ == "__main__":
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        init()
