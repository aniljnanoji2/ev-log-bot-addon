from unittest import result
import requests
import json
from dotenv import load_dotenv
import os
import base64

# keep-alive: updated to prevent workflow disable

load_dotenv(override=True)

# --- Environment Variables ---
scooter_id = os.getenv("scooter_id")
api_token = os.getenv("api_token")
webhook_url = os.getenv("webhook_url")


def get_scooter_details(scooter_id, api_token, limit=None, sort_order="asc"):
    """
    Fetches the trip logs for a given scooter ID and returns the scooter's display ID.
    Includes error handling for API failures and empty results.
    """
    url = f"https://cerberus.ather.io/api/v1/triplogs?scooter={scooter_id}&sort=start_time_tz%20{sort_order}"
    headers = {"Authorization": f"Bearer {api_token}"}
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
        
        result = response.json()
        
        # --- FIX: Check if the 'result' list is empty before accessing index 0 ---
        if result:
            # The line that was causing the IndexError
            display_id = result[0]["scooter"]["display_id"][2:]
            print(f"INFO: Successfully retrieved Scooter Display ID: {display_id}")
            return display_id
        else:
            # This handles the case where the API returns a 200 OK but an empty list
            print(f"ERROR: API returned empty trip logs for scooter ID: {scooter_id}. Check if the scooter_id is correct.")
            return None
        # --- END OF FIX ---
        
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Request error fetching trip logs for scooter {scooter_id}. Status: {response.status_code if 'response' in locals() else 'N/A'}. Details: {e}")
        return None


def get_ride_details(scooter_display_id, api_token, limit=None, sort_order="asc"):
    """
    Fetches ride details using the scooter display ID.
    """
    if not scooter_display_id:
        print("WARNING: Cannot fetch ride details. Scooter Display ID is missing.")
        return None
    
    url = f"https://cerberus.ather.io/api/v1/rides?scooterid={scooter_display_id}&limit={limit}&sort=ride_start_time%20{sort_order}"
    headers = {"Authorization": f"Bearer {api_token}"}
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        # Assuming the response structure is {'data': {'trips': [...]}}
        result = response.json()["data"]["trips"]
        return result
    
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Request error fetching ride details for scooter {scooter_display_id}. Details: {e}")
        return None
    except KeyError:
        print(f"ERROR: API response structure changed or missing 'data'/'trips' key.")
        return None


def update_ghseet_data(rides):
    """
    Processes new ride data and sends updates to the Google Apps Script webhook.
    """
    if not rides:  # Check if rides is empty
        print("No ride data to process.")
        return

    # --- Fetch existing IDs from Google Sheet ---
    get_id_url = f"{webhook_url}?getids=true"
    try:
        get_id_response = requests.get(get_id_url)
        get_id_response.raise_for_status()
        ids_from_sheet = get_id_response.json()
        ids_from_sheet_set = set(ids_from_sheet)
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Could not fetch existing IDs from Google Sheet webhook. Details: {e}")
        return
    except json.JSONDecodeError:
        print("ERROR: Failed to decode JSON from Google Sheet IDs response.")
        return


    ids_from_ride_data = [ride["ride_id"] for ride in rides]

    # Find new IDs that are not in ids_from_sheet
    new_ids = sorted([id for id in ids_from_ride_data if id not in ids_from_sheet_set])
    print(f"Found {len(new_ids)} new rides to process.")

    # Extract dictionary values for new IDs
    new_ride_data = sorted([ride for ride in rides if ride["ride_id"] in new_ids], key=lambda x: x["ride_id"])

    if not new_ride_data:  # Check if there are new rides to send
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
        # Ensure encoding/decoding is correct for transport
        encoded_data = base64.b64encode(data.encode('utf-8')).decode('utf-8') 
        params = {"rideData": encoded_data, "telegramAlert": str(telegram_alert).lower()}

        try:
            # Post request sends parameters in JSON body
            response = requests.post(webhook_url, json=params)
            response.raise_for_status()
            print(f"Response from Google Apps Script for ride ID {ride['ride_id']}: {response.text}")
        except requests.exceptions.RequestException as e:
            print(f"Request error for ride ID {ride['ride_id']}: {e}")
            
            
# --- Main Execution Block ---

# 1. Get the scooter display ID. This is the previously failing step.
scooter_display_id = get_scooter_details(scooter_id, api_token, 1, "desc")

# 2. Add a check here to ensure the display ID was successfully retrieved before proceeding.
if scooter_display_id:
    # 3. Get the ride data using the display ID
    ride_data = get_ride_details(scooter_display_id, api_token, 20, "desc")
    
    # 4. Update the Google Sheet
    update_ghseet_data(ride_data)
else:
    print("Workflow terminated: Failed to retrieve necessary scooter ID.")
