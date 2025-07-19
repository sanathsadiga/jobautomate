from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import time

def open_zoho_job_page(job_url, resume_path):
    chrome_options = Options()
    chrome_options.add_argument("--start-maximized")
    # chrome_options.add_argument("--disable-gpu")  # Optional for Windows

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    try:
        driver.get(job_url)
        wait = WebDriverWait(driver, 20)

        # ✅ Step 1: Click "I'm interested" button
        button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(., \"I'm interested\")]")))
        button.click()
        print("✅ Clicked 'I'm interested' button")

        # ✅ Step 2: Upload Resume
        upload_field = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type="file"]')))
        upload_field.send_keys(resume_path)
        print("✅ Resume uploaded. Waiting for parsing...")

        # ✅ Give time for parsing
        time.sleep(10)

        print("✅ Resume parsed. Browser will stay open for review.")
        return {"status": "success", "message": "Resume uploaded. Browser is open for manual review."}

    except Exception as e:
        print(f"❌ Error: {e}")
        return {"status": "error", "message": str(e)}

    # ❌ Do NOT close the browser here
    # finally:
    #     driver.quit()
