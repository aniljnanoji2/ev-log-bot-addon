from unittest import result
import requests
import json
from dotenv import load_dotenv
import os
import base64

load_dotenv(override=True)

scooter_id = os.getenv("scooter_id")
api_token = os.getenv("api_token")
webhook_url = os.getenv("webhook_url")


def get_scooter_details(scooter_id, api_token, limit=None, sort_order="asc"):
    url = f"https://cerberus.ather.io/api/v1/triplogs?scooter={scooter_id}&sort=start_time_tz%20{sort_order}"
    headers = {"Authorization": f"Bearer {api_token}"}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        result = response.json()
        display_id = result[0]["scooter"]["display_id"][2:]
        return display_id
    else:
        print(f"Error fetching trip logs for scooter {scooter_id}: {response.status_code}")
        return None


def get_ride_details(scooter_display_id, api_token, limit=None, sort_order="asc"):
    url = f"https://cerberus.ather.io/api/v1/rides?scooterid={scooter_display_id}&limit={limit}&sort=ride_start_time%20{sort_order}"
    headers = {"Authorization": f"Bearer {api_token}"}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        result = response.json()["data"]["trips"]
        return result
    else:
        print(f"Error fetching trip logs for scooter {scooter_display_id}: {response.status_code}")
        return None


def update_ghseet_data(rides):
    if not rides:  # Check if rides is empty
        print("No ride data to process.")
        return

    get_id_url = f"{webhook_url}?getids=true"
    get_id_response = requests.get(get_id_url)
    ids_from_sheet = get_id_response.json()
    ids_from_sheet_set = set(ids_from_sheet)

    ids_from_ride_data = [ride["ride_id"] for ride in rides]

    # Find new IDs that are not in ids_from_sheet
    new_ids = sorted([id for id in ids_from_ride_data if id not in ids_from_sheet_set])
    print("New IDs:", new_ids)

    # Extract dictionary values for new IDs
    new_ride_data = sorted([ride for ride in rides if ride["ride_id"] in new_ids], key=lambda x: x["ride_id"])

    if not new_ride_data:  # Check if there are new rides to send
        print("No new ride data to send.")
        return

    # Set telegram alerts only for the last 5 if there are more than 10 new rides
    alert_threshold = 10
    alert_tail = 5
    ride_count = len(new_ride_data)

    for i, ride in enumerate(new_ride_data):
        # Logic: only alert for last 5 if ride count is more than 10
        if ride_count > alert_threshold:
            telegram_alert = i >= (ride_count - alert_tail)
        else:
            telegram_alert = True

        data = json.dumps(ride)
        encoded_data = base64.b64encode(data.encode()).decode()
        params = {"rideData": encoded_data, "telegramAlert": str(telegram_alert).lower()}

        try:
            response = requests.post(webhook_url, json=params)
            response.raise_for_status()
            print(f"Response from Google Apps Script for ride ID {ride['ride_id']} {response.text}")
        except requests.exceptions.RequestException as e:
            print(f"Request error for ride ID {ride['ride_id']}")


scooter_display_id = get_scooter_details(scooter_id, api_token, 1, "desc")
# get this scooter_display_id once and store it for future use
# print(f"Scooter Display ID: {scooter_display_id}")
ride_data = get_ride_details(scooter_display_id, api_token, 20, "desc")
update_ghseet_data(ride_data)
