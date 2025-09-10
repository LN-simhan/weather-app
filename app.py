import tkinter as tk
from tkinter import messagebox
import json
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import pandas as pd
import matplotlib.pyplot as plt
import requests
from datetime import datetime, timedelta, timezone
import openmeteo_requests
import pandas as pd
import requests_cache
from retry_requests import retry
import os

from dotenv import load_dotenv
load_dotenv()

def get_lat_long(place):
    # Define the API endpoint URL
    url = "https://photon.komoot.io/api/"
    params = {
        "q":place
    }

    response = requests.get(url,params=params)
    if response.status_code == 200:
        data = response.json()
        latitude = data["features"][0]["geometry"]["coordinates"][0]
        longitude = data["features"][0]["geometry"]["coordinates"][1]
        return latitude,longitude
    else:
        print(f"Error: {response.status_code} - {response.text}")

def get_today_older_date():
    gmt_offset = timezone(timedelta(hours=5.5))
    current_date = datetime.now(gmt_offset)

    # Get today's and yesterday's date in YYYY-MM-DD format
    today = current_date.date()
    yesterday = (current_date - timedelta(days=15)).date()

    return today.isoformat(), yesterday.isoformat()

def get_current_weather(place):
    long,lat = get_lat_long(place)
    url = "https://api.openweathermap.org/data/2.5/weather"
    print(f"latitude {lat}, longitude {long}")
    params = {
        "lat":lat,
        "lon":long,
        "appid":os.getenv("API_KEY"),
        "units":"metric"
    }

    # Make the GET request
    response = requests.get(url,params=params)
    if response.status_code == 200:
        data = response.json()
        with open("output/data/data.json","w") as f:
            json.dump(data,f,indent=4)
    else:
        print(f"Error: {response.status_code} - {response.text}")
    cloud = data["clouds"]["all"]
    humidity = data["main"]["humidity"]
    maxTemp = data["main"]["temp_max"]
    minTemp = data["main"]["temp_min"]
    actualTemp = data["main"]["feels_like"]
    rain = data.get("rain", {}).get("1h", 0)
    description_rain = interpret_weather_by_rain(rain)
    description_cloud = interpret_weather_by_clouds(cloud)
    description_humidity = interpret_weather_by_humidity(humidity)
    description_temperature = interpret_temperature_celsius(actualTemp)
    print(f"Cloud Cover: {cloud}% → {description_cloud}")
    print(f"Humidity: {humidity}% → {description_humidity}")
    print(f"The Max and Min temperature are {maxTemp}C and {minTemp}C respectively but it acutally feels like {actualTemp}C")
    print(f"Rain measure :{rain} mm/hr -> {description_rain}")
    data = {
        "Cloud": {
            "cover percentage" : cloud,
            "overview": description_cloud
        },
        "Humidity": {
            "humidity percentage" : humidity,
            "overview" : description_humidity
        },
        "Rain": {
            "rain measure in mm/hr" : rain,
            "overview" : description_rain
        },
        "Temperature" : {
            "temperature in celcius": actualTemp,
            "overview": description_temperature
        }
    }
    json_str = json.dumps(data)
    outputString = f"Cloud Cover: {cloud}% → {description_cloud} \n"+f"Humidity: {humidity}% → {description_humidity} \n"+f"The temperature feels like {actualTemp} -> {description_temperature}\n"+f"Rain measure :{rain} mm/hr -> {description_rain}"
    return json_str , outputString

def get_historic_data(place):
    lat,long = get_lat_long(place)
    today, n_days_ago_date = get_today_older_date()

    cache_session = requests_cache.CachedSession('.cache', expire_after = 3600)
    retry_session = retry(cache_session, retries = 5, backoff_factor = 0.2)
    openmeteo = openmeteo_requests.Client(session = retry_session)

    # Make sure all required weather variables are listed here
    # The order of variables in hourly or daily is important to assign them correctly below
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": long,
        "daily": ["temperature_2m_max", "temperature_2m_min", "rain_sum", "precipitation_sum", "wind_speed_10m_max"],
        "start_date": n_days_ago_date,
        "end_date": today,
    }
    responses = openmeteo.weather_api(url, params=params)

    response = responses[0]
    print(f"Coordinates: {response.Latitude()}°N {response.Longitude()}°E")

    # Process daily data. The order of variables needs to be the same as requested.
    daily = response.Daily()
    daily_temperature_2m_max = daily.Variables(0).ValuesAsNumpy()
    daily_temperature_2m_min = daily.Variables(1).ValuesAsNumpy()
    daily_rain_sum = daily.Variables(2).ValuesAsNumpy()
    daily_precipitation_sum = daily.Variables(3).ValuesAsNumpy()
    daily_wind_speed_10m_max = daily.Variables(4).ValuesAsNumpy()

    daily_data = {"date": pd.date_range(
        start = pd.to_datetime(daily.Time(), unit = "s", utc = True),
        end = pd.to_datetime(daily.TimeEnd(), unit = "s", utc = True),
        freq = pd.Timedelta(seconds = daily.Interval()),
        inclusive = "left"
    )}

    daily_data["temperature_2m_max"] = daily_temperature_2m_max
    daily_data["temperature_2m_min"] = daily_temperature_2m_min
    daily_data["rain_sum"] = daily_rain_sum
    daily_data["precipitation_sum"] = daily_precipitation_sum
    daily_data["wind_speed_10m_max"] = daily_wind_speed_10m_max
    daily_dataframe = pd.DataFrame(data = daily_data)
    return daily_dataframe

def interpret_weather_by_clouds(cloud_percentage: float) -> str:
    """
    Returns a weather description based on cloud cover percentage.

    :param cloud_percentage: Cloud cover as a percentage (0 to 100)
    :return: Description string
    """
    if cloud_percentage < 0 or cloud_percentage > 100:
        return "Invalid cloud percentage"

    if cloud_percentage < 10:
        return "Clear sky"
    elif cloud_percentage < 25:
        return "Mostly clear with few clouds"
    elif cloud_percentage < 50:
        return "Partly cloudy"
    elif cloud_percentage < 70:
        return "Mostly cloudy"
    elif cloud_percentage < 90:
        return "Overcast"
    else:
        return "Heavy clouds / Possible thunderstorms"
    
def interpret_weather_by_humidity(humidity_percentage: float) -> str:
    """
    Returns a weather description based on humidity percentage.

    :param humidity_percentage: Humidity as a percentage (0 to 100)
    :return: Description string
    """
    if humidity_percentage < 0 or humidity_percentage > 100:
        return "Invalid humidity percentage"
    if humidity_percentage < 10:
        return "Very low"
    elif humidity_percentage < 50:
        return "Low"
    elif humidity_percentage < 75:
        return "Moderate"
    elif humidity_percentage < 90:
        return "High"
    else:
        return "Very High"
    
def interpret_weather_by_rain(rain_measure: float) -> str:
    """
    Returns a weather description based on rain measure in mm/hr.

    :param rain_measure: rain measure in millimeter per hour
    :return: Description string
    """
    if rain_measure < 0 or rain_measure > 100:
        return "Invalid humidity percentage"
    if rain_measure < 2.5:
        return "Light or no rain"
    elif rain_measure > 2.5 and rain_measure < 7.5:
        return "Moderate rain, carry an umbrella"
    elif rain_measure > 7.5:
        return "Heavy rain, lookout for shelter"
    elif rain_measure > 50:
        return "Violent rains, adviced to stay at home"

def interpret_temperature_celsius(temp_c: float) -> str:
    """
    Returns a weather description based on temperature in Celsius.

    :param temp_c: Temperature in degrees Celsius
    :return: Description string
    """
    if temp_c < -50 or temp_c > 60:
        return "Invalid temperature value"
    elif temp_c <= 0:
        return "Freezing cold"
    elif 0 < temp_c <= 10:
        return "Very cold"
    elif 10 < temp_c <= 20:
        return "Cool weather"
    elif 20 < temp_c <= 25:
        return "Comfortable temperature"
    elif 25 < temp_c <= 30:
        return "Warm weather"
    elif 30 < temp_c <= 35:
        return "Hot weather"
    elif temp_c > 35:
        return "Very hot! Stay hydrated"

# Single plot function to produce a graph
def single_plot(fig,place):
    daily_dataframe = get_historic_data(place)
    daily_dataframe["date"] = pd.to_datetime(daily_dataframe["date"])
    
    ax1 = fig.add_subplot(111)

    # Plot max and min temperatures on ax1
    ax1.plot(daily_dataframe["date"], 
             daily_dataframe["temperature_2m_max"], 
             label="Max Temp (°C)", color='red', marker='o')
    
    ax1.plot(daily_dataframe["date"], 
             daily_dataframe["temperature_2m_min"], 
             label="Min Temp (°C)", color='orange', marker='o')
    
    ax1.set_ylabel("Temperature (°C)", color='darkred')
    ax1.set_xlabel("Date")
    ax1.tick_params(axis='y', labelcolor='darkred')
    
    # Create secondary y-axis for rainfall
    ax2 = ax1.twinx()
    ax2.bar(daily_dataframe["date"], 
            daily_dataframe["rain_sum"], 
            width=0.5, alpha=0.4, color='blue', label="Rainfall (mm)")
    
    ax2.set_ylabel("Rainfall (mm)", color='blue')
    ax2.tick_params(axis='y', labelcolor='blue')
    
    # Date formatting
    fig.autofmt_xdate()
    
    # Add legends combining lines and bars
    lines, labels = ax1.get_legend_handles_labels()
    bars, bar_labels = ax2.get_legend_handles_labels()
    ax1.legend(lines + bars, labels + bar_labels, loc="upper left",fontsize='xx-small')
    
    # Set title
    fig.suptitle("15 days Max/Min Temperature and Rainfall correlation")
    
    # Tight layout to prevent clipping
    fig.tight_layout()

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Weather App")
        self.output_data = None

        # Header label
        header = tk.Label(root, text="Basic Weather Search Application", font=("Helvetica", 16))
        header.pack(pady=10)

        # Input label and entry box
        input_frame = tk.Frame(root)
        input_frame.pack(pady=5)
        tk.Label(input_frame, text="Enter place here:").pack(side=tk.LEFT)
        self.input_entry = tk.Entry(input_frame, width=40)
        self.input_entry.pack(side=tk.LEFT, padx=5)

        # Search button
        search_btn = tk.Button(root, text="Search", command=self.perform_search)
        search_btn.pack(pady=5)

        # Frame for Summary output
        summary_frame = tk.Frame(root)
        summary_frame.pack(pady=5)
        tk.Label(summary_frame, text="Summary", font=("Helvetica", 14)).pack()
        self.summary_text = tk.Text(summary_frame, height=4, width=100)
        self.summary_text.pack()

        # Frame for JSON output
        json_frame = tk.Frame(root)
        json_frame.pack(pady=5)
        tk.Label(json_frame, text="Json", font=("Helvetica", 14)).pack()
        self.json_text = tk.Text(json_frame, height=10, width=100)
        self.json_text.pack()

        # Frame to hold Matplotlib plot
        self.plot_frame = tk.Frame(root)
        self.plot_frame.pack(pady=10)

        # Download button
        download_btn = tk.Button(root, text="Download JSON Output", command=self.download_json)
        download_btn.pack(pady=5)

    def perform_search(self):
        input_text = self.input_entry.get().strip()
        if not input_text:
            messagebox.showwarning("Input needed", "Please enter place to search.")
            return

        # Call multiple functions and gather results
        result = get_current_weather(input_text)
        json_str = result[0]
        outputString = result[1]
        self.output_data = {
            "Summary": outputString,
            "Json": json_str,
        }

        # Display output in text widget
        # Clear previous outputs
        self.summary_text.delete("1.0", tk.END)
        self.json_text.delete("1.0", tk.END)

        # Insert Summary text
        self.summary_text.insert(tk.END, outputString)

        # Pretty-print JSON string and insert into json_text box
        parsed_json = json.loads(json_str)
        pretty_json = json.dumps(parsed_json, indent=4)
        self.json_text.insert(tk.END, pretty_json)

        # Clear previous plot
        for widget in self.plot_frame.winfo_children():
            widget.destroy()

        # Create single Matplotlib figure and embed in Tkinter
        fig = Figure(figsize=(7, 3), dpi=100)
        single_plot(fig,input_text)
        canvas = FigureCanvasTkAgg(fig, master=self.plot_frame)
        canvas.draw()
        canvas.get_tk_widget().pack()

    def download_json(self):
        if not self.output_data["Json"]:
            messagebox.showinfo("No Data", "No output to download. Please perform a search first.")
            return
        try:
            # converting it to python dictionary for properly store it in json using json dump
            json_obj = json.loads(self.output_data["Json"])
            with open("output/data/weather_data.json", "w") as f:
                json.dump(json_obj, f, indent=4)
            messagebox.showinfo("Success", "Output JSON saved to weather_data.json")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save JSON file: {e}")


if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()
