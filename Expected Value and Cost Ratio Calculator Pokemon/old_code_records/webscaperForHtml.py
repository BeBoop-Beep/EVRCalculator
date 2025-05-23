import random
import time
from playwright.sync_api import sync_playwright

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Safari/605.1.15",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1"
]

def human_like_delay():
    """Random delays that mimic human browsing patterns"""
    time.sleep(random.uniform(1.5, 4.5))

def human_like_scroll(page):
    """Smooth scrolling behavior with random pauses"""
    scroll_distance = random.randint(300, 800)
    scroll_duration = random.randint(200, 800)
    
    for _ in range(random.randint(3, 6)):
        page.evaluate(f"""
            window.scrollBy({{
                top: {scroll_distance},
                left: 0,
                behavior: 'smooth'
            }});
        """)
        human_like_delay()

def scrape_tcgplayer(setURL):
    url = setURL
    html_output = "page_content.html"
    
    with sync_playwright() as p:
        user_agent = random.choice(USER_AGENTS)
        browser = p.chromium.launch(headless=False)  # Visible for debugging
        context = browser.new_context(
            user_agent=user_agent,
            viewport={'width': 1920, 'height': 1080},
            locale='en-US',
            timezone_id='America/New_York'
        )
        page = context.new_page()

        try:
            # Simulate human navigation
            print(f"Loading {url}...")
            page.goto(url, timeout=60000, wait_until="domcontentloaded")
            human_like_delay()

            # Take initial screenshot for debugging
            page.screenshot(path="initial_load.png")
            print("Initial page loaded - screenshot saved")

            # Handle potential popups
            try:
                page.click('button:has-text("Accept")', timeout=3000)
                print("Accepted cookies")
                human_like_delay()
            except:
                print("No cookie popup found")
                pass

            # Wait for core content
            print("Waiting for content to load...")
            page.wait_for_selector('tbody.tcg-table-body', state='attached', timeout=15000)
            human_like_delay()

            # Human-like scrolling
            print("Simulating human scrolling...")
            human_like_scroll(page)

            # Final screenshot after interactions
            page.screenshot(path="after_scrolling.png")
            print("Scrolling complete - screenshot saved")

            # Get the full page HTML
            html_content = page.content()
            
            # Save full HTML to file
            with open(html_output, "w", encoding="utf-8") as f:
                f.write(html_content)
            print(f"\nSuccessfully saved HTML to {html_output}")

        except Exception as e:
            print(f"Error occurred: {str(e)}")
            page.screenshot(path="error.png")
            print("Error screenshot saved")
        finally:
            context.close()
            browser.close()
            print("Browser closed")

