import requests

class TCGPlayerClient:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/113.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Referer": "https://www.tcgplayer.com/"
        }
    
    def fetch_price_data(self, price_guide_url):
        """Fetch price data from TCGPlayer API"""
        response = requests.get(price_guide_url)
        if response.status_code != 200:
            raise Exception(f"Error fetching data: {response.status_code}")
        return response.json()
    
    def fetch_product_market_price(self, price_url):
        """Fetch market price for a sealed product"""
        response = requests.get(price_url, headers=self.headers)
        if response.status_code != 200:
            print(f"Failed to fetch data from {price_url}: {response.status_code}")
            return None
        
        try:
            data = response.json()
            first_market_price = data.get("result", [])[0].get("buckets", [])[0].get("marketPrice", None)
            return first_market_price
        except (IndexError, AttributeError, ValueError) as e:
            print(f"Error parsing data from {price_url}: {e}")
            return None