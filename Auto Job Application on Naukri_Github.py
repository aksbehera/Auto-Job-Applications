#!/usr/bin/env python
# coding: utf-8

# IMPORT THE NECESSARY LIBRARIES

# In[ ]:


# Importing the necessary libraries
import selenium
from selenium import webdriver as wb
import pandas as pd
import time
from time import sleep
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC


# CODES

# In[ ]:


# Chaning the working directory to the path where the chromedriver is saved & setting up the chrome driver
import time
start_time = time.time()
get_ipython().run_line_magic('cd', '"PATH WHERE YOUR CHROMEDRIVER IS SAVED"')
driver = wb.Chrome("PATH WHERE YOUR CHROMEDRIVER IS SAVED\\chromedriver.exe")
Skillset = ['Analysis','Python','SQL']
Skillset = [x.lower() for x in Skillset]
LL = 15
UL = 25
location = 'Bangalore'
location = location.lower().replace(" ","-")
role = 'Data Analyst'
role = role.lower().replace(" ","-")
driver.get("https://www.naukri.com/data-analyst-jobs-in-delhi-ncr?k=data%20analyst&l=delhi%2Fncr")
driver.find_element_by_xpath('//*[@id="login_Layer"]/div').click()
time.sleep(5)
driver.find_element_by_xpath('//*[@id="root"]/div[2]/div[2]/div/form/div[2]/input').send_keys('YOUR NAUKRI LOGIN')
driver.find_element_by_xpath('//*[@id="root"]/div[2]/div[2]/div/form/div[3]/input').send_keys('YOUR NAUKRI PASSWORD.')
time.sleep(5)
driver.find_element_by_xpath('//*[@id="root"]/div[2]/div[2]/div/form/div[6]/button').click()
time.sleep(5)
app = pd.DataFrame()

for i in range(1,6):
    try:
        driver.get('https://www.naukri.com/'+role+'-jobs-in-'+location+'-'+str(i)+'?ctcFilter='+str(LL)+'to'+str(UL))
    except:
        driver.get('https://www.naukri.com/'+role+'-jobs-in-'+location+'?ctcFilter='+str(LL)+'to'+str(UL))

    for i in range(1,20):
        try:
            WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.XPATH, '//*[@id="root"]/div[3]/div[2]/section[2]/div[2]/article['+str(i)+']/div[1]/div[1]/a'))).click()
        except:
            WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.XPATH, '//*[@id="root"]/div[3]/div[2]/section[2]/div[2]/article['+str(i)+']/div[1]/div/a'))).click()
        driver.switch_to.window(driver.window_handles[1])
        url = driver.current_url
        driver.get(url)
        try:
            test = driver.find_element_by_xpath('//*[@id="root"]/main/div[2]/div[2]/section[2]')
            if all(word in test.text.lower() for word in Skillset):
                Title = driver.find_element_by_xpath('//*[@id="root"]/main/div[2]/div[2]/section[1]/div[1]/div[1]/header/h1')
                Title = Title.text
                Title = pd.Series(Title)
                Company = driver.find_element_by_xpath('//*[@id="root"]/main/div[2]/div[2]/section[1]/div[1]/div[1]/div/a[1]')
                Company = Company.text
                Company = pd.Series(Company)
                loc = driver.find_element_by_xpath('//*[@id="root"]/main/div[2]/div[2]/section[1]/div[1]/div[2]/div[3]/span/a')
                loc = loc.text
                loc = pd.Series(loc)
                df = pd.DataFrame({'Title':Title,'Company':Company,'Location':loc})
                app = app.append(df)
                driver.find_element_by_xpath('//*[@id="root"]/main/div[2]/div[2]/section[1]/div[1]/div[3]/div/button[2]').click()
                time.sleep(2)
                driver.close()
                driver.switch_to.window(driver.window_handles[0])
            else:
                driver.close()
                driver.switch_to.window(driver.window_handles[0])
        except:
            driver.close()
            driver.switch_to.window(driver.window_handles[0])
app


# In[ ]:


print(str(len(app))+" applications done in %s seconds" % (time.time() - start_time))

