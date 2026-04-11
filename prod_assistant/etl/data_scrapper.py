import csv
import time
import re
import os
from bs4 import BeautifulSoup
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


class FlipkartScraper:
    def __init__(self, output_dir):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def _make_driver(self):
        """Create a Chrome driver with all necessary options."""
        options = uc.ChromeOptions()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--remote-debugging-port=0")
        return uc.Chrome(options=options, use_subprocess=True, version_main=147)

    def _close_popup(self, driver):
        """Try multiple selectors to close the login popup."""
        popup_selectors = [
            (By.XPATH, "//button[contains(text(), '✕')]"),
            (By.XPATH, "//button[contains(text(), '×')]"),
            (By.CSS_SELECTOR, "button._2KpZ6l._2doB4z"),
            (By.XPATH, "//button[@class and contains(@class,'close')]"),
        ]
        for by, selector in popup_selectors:
            try:
                driver.find_element(by, selector).click()
                time.sleep(1)
                return
            except Exception:
                continue

    def get_top_reviews(self, product_url, count=2):
        if not product_url.startswith("http"):
            return "No reviews found"

        # ✅ Go directly to reviews page
        reviews_url = product_url.replace("/p/", "/product-reviews/")

        driver = self._make_driver()
        try:
            driver.get(reviews_url)
            time.sleep(5)
            self._close_popup(driver)

            for _ in range(3):
                ActionChains(driver).send_keys(Keys.END).perform()
                time.sleep(1.5)

            soup = BeautifulSoup(driver.page_source, "html.parser")

            review_blocks = (
                soup.select("span.css-1jxf684") or
                soup.select("div.t-ZTKy") or
                soup.select("div._27M-vq") or
                soup.select("div[class*='review']")
            )

            seen = set()
            reviews = []
            for block in review_blocks:
                text = block.get_text(separator=" ", strip=True)
                if text and text not in seen and len(text) > 10:  # skip very short texts
                    reviews.append(text)
                    seen.add(text)
                if len(reviews) >= count:
                    break

        except Exception as e:
            print(f"Review scraping error: {e}")
            reviews = []
        finally:
            driver.quit()

        return " || ".join(reviews) if reviews else "No reviews found"

    def scrape_flipkart_products(self, query, max_products=1, review_count=2):
        """Scrape Flipkart products based on a search query."""
        driver = self._make_driver()
        search_url = f"https://www.flipkart.com/search?q={query.replace(' ', '+')}"
        products = []

        try:
            driver.get(search_url)

            # Wait until product cards load
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-id]"))
            )

            self._close_popup(driver)
            time.sleep(2)

            soup = BeautifulSoup(driver.page_source, "html.parser")
            product_cards = soup.select("div[data-id]")[:max_products]

            for card in product_cards:
                try:
                    # ✅ Updated selectors from your inspected HTML
                    title_el = card.select_one("div.RG5Slk")
                    title = title_el.get_text(strip=True) if title_el else "N/A"

                    price_el = card.select_one("div.hZ3P6w")
                    price = price_el.get_text(strip=True) if price_el else "N/A"

                    rating_el = card.select_one("div.MKiFS6")
                    # Remove the star image text, keep only the number
                    rating = rating_el.get_text(strip=True) if rating_el else "N/A"

                    reviews_el = card.select_one("span.PvbNMB")
                    reviews_raw = reviews_el.get_text(separator=" ", strip=True) if reviews_el else ""

                    # Extract review count — "2,18,124 Ratings & 7,055 Reviews"
                    review_match = re.search(r"([\d,]+)\s+Reviews", reviews_raw)
                    total_reviews = review_match.group(1) if review_match else "N/A"

                    # Get product link
                    link_el = card.select_one("a[href*='/p/']")
                    href = link_el["href"] if link_el else ""
                    product_link = href if href.startswith("http") else "https://www.flipkart.com" + href

                    # Extract product ID
                    id_match = re.findall(r"/p/(itm[0-9A-Za-z]+)", href)
                    product_id = id_match[0] if id_match else "N/A"

                except Exception as e:
                    print(f"Error processing card: {e}")
                    continue

                top_reviews = (
                    self.get_top_reviews(product_link, count=review_count)
                    if "flipkart.com" in product_link
                    else "Invalid product URL"
                )

                products.append([product_id, title, rating, total_reviews, price, top_reviews])

        except Exception as e:
            print(f"Scraping failed: {e}")
        finally:
            driver.quit()

        return products

    def save_to_csv(self, data, filename="product_reviews.csv"):
        """Save the scraped product reviews to a CSV file."""
        if os.path.isabs(filename):
            path = filename
        elif os.path.dirname(filename):
            path = filename
            os.makedirs(os.path.dirname(path), exist_ok=True)
        else:
            path = os.path.join(self.output_dir, filename)

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["product_id", "product_title", "rating", "total_reviews", "price", "top_reviews"])
            writer.writerows(data)