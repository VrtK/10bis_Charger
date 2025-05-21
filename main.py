import pickle
import logging
import requests

logger = logging.getLogger('10bis_charger')
logging.basicConfig(
    format='%(asctime)s %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('10bis_charger.log', 'a', 'utf-8'),
        logging.StreamHandler()
    ]
)

session = requests.Session()
filename = 'cookies.pkl'

BASE_HEADERS = {
    "x-app-type": "web",
    "User-Agent": "Mozilla/5.0",
    "Content-Type": "application/json",
    "Origin": "https://www.10bis.co.il",
}


def save_cookies():
    with open(filename, 'wb') as f:
        pickle.dump(session.cookies, f)


def login_flow(email_address):
    logging.info(f'Starting login flow for {email_address}')
    url = "https://www.10bis.co.il/NextApi/GetUserAuthenticationDataAndSendAuthenticationCodeToUser"
    payload = {
        "culture": "he-IL",
        "uiCulture": "he",
        "email": email_address
    }
    response = session.post(url, headers=BASE_HEADERS, json=payload)
    data = response.json()
    if data.get('Success'):
        logging.info('Email verified successfully')
        auth_data = data['Data']['codeAuthenticationData']
        return data['ShoppingCartGuid'], auth_data['authenticationToken']
    else:
        logging.error(f"Login failed, {response.status_code} {response.text}")
        return False, None


def generate_token(auth_code, auth_token, shopping_guid, email_address):
    logging.info('Generating Token')
    url = "https://www.10bis.co.il/NextApi/GetUserV2"
    data = {
        "shoppingCartGuid": shopping_guid,
        "culture": "he-IL",
        "uiCulture": "he",
        "email": email_address,
        "authenticationToken": auth_token,
        "authenticationCode": auth_code
    }
    response = session.post(url, headers=BASE_HEADERS, json=data)
    data = response.json()
    if data.get('Success'):
        session_token = data['Data']['sessionToken']
        logging.info(f'Success, session token: {session_token}')
        save_cookies()
        return session_token
    else:
        logging.error(f"Token generation failed: {response.status_code} {response.text}")
        return False


def get_credit_cards():
    logging.info('Resolving credit card list')
    url = "https://www.10bis.co.il/NextApi/UserTransactionsReport"
    data = {
        "culture": "he-IL",
        "uiCulture": "he",
        "dateBias": "0"
    }
    response = session.post(url, headers=BASE_HEADERS, json=data)
    data = response.json()
    if data.get('Success'):
        for credit_card in data['Data']['moneycards']:
            card_id = credit_card['moneycardId']
            logging.info(f'Checking card #{card_id}')
            conversion = credit_card.get('tenbisCreditConversion', {})
            if conversion.get('isEnabled'):
                amount = conversion.get("availableAmount", 0)
                logging.info(f'{card_id} can be charged in ₪{amount}')
                return card_id, amount
    logging.error('No eligible credit cards found')
    return False, 0


def card_charge(card_id, amount):
    logging.info(f'Charging card_id #{card_id} with ₪{amount}')
    url = "https://api.10bis.co.il/api/v1/Payments/LoadTenbisCredit"

    options_headers = {
        "Host": "api.10bis.co.il",
        "Connection": "keep-alive",
        "Accept": "*/*",
        "Access-Control-Request-Method": "PATCH",
        "Access-Control-Request-Headers": "content-type,language,x-app-type",
        "Origin": "https://www.10bis.co.il",
        "User-Agent": "Mozilla/5.0",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "Sec-Fetch-Dest": "empty",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "en,he;q=0.9,en-US;q=0.8,und;q=0.7"
    }

    session.options(url, headers=options_headers)

    patch_headers = {
        **BASE_HEADERS,
        "language": "he"
    }

    data = {"amount": amount, "moneycardIdToCharge": card_id}
    response = session.patch(url, headers=patch_headers, json=data)
    if response.status_code == 200:
        logging.info('Charge successfully!')
    else:
        logging.error(f"Charge failed: {response.status_code} {response.text}")


if __name__ == '__main__':
    try:
        with open(filename, 'rb') as d:
            session.cookies.update(pickle.load(d))
    except FileNotFoundError:
        logging.info("Cookie jar is empty!")
        email = input('Insert Email address:\n')
        shopping_guid, token = login_flow(email)
        if not token:
            exit(1)
        code = input('Insert SMS verification code:\n')
        session_token = generate_token(code, token, shopping_guid, email)
        if not session_token:
            exit(1)

    card_id, available_amount = get_credit_cards()
    if available_amount > 0:
        card_charge(card_id, available_amount)
