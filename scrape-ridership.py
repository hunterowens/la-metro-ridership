"""
Scrape Los Angeles Metro ridership data,
leaving it in a relatively raw state.
"""
import datetime

import bs4
import pandas as pd
import requests
import warnings

# Ignore SSL warnings
warnings.filterwarnings("ignore")

# The URL for the ridership form
RIDERSHIP_URL = "https://isotp.metro.net/MetroRidership/IndexSys.aspx"

# Parameters needed to validate the request
ASPX_PARAMETERS = ["__VIEWSTATE", "__EVENTVALIDATION"]

# The S3 bucket into which to load data.
S3_BUCKET = "s3://tmf-ita-data"


def get_form_data():
    """
    Make an inital fetch of the form so we can scrape the options
    as well as the parameters needed to validate our requests.
    """
    # Fetch the page and parse it. Metro needs to get their SSL
    # game in order, but until then, we need verify=False
    r = requests.get(RIDERSHIP_URL, verify=False)
    r.raise_for_status()
    soup = bs4.BeautifulSoup(r.text, features="html.parser")

    # Get validation info
    aspx_data = {
        param: soup.find(attrs={"id": param}).attrs.get("value", "")
        for param in ASPX_PARAMETERS
    }

    # Get all of the metro lines
    line_options = soup.find(attrs={"id": "ContentPlaceHolder1_lbLines"}).select(
        "option"
    )
    lines = [
        option.attrs["value"]
        for option in line_options
        if option.attrs["value"] != "All"
    ]

    # Get the available years
    year_options = soup.find(attrs={"id": "ContentPlaceHolder1_ddlYear"}).select(
        "option"
    )
    years = [option.attrs["value"] for option in year_options]
    return lines, years, aspx_data


def submit_form(year, period, line, aspx_data):
    """
    Submit a form to the Metro ridership site requesting data for a line.

    Parameters
    ----------
    year: int
        The year for which to fetch the data.
    period: str or int
        The time period in which to fetch the data. Typically you will want
        an integer month, though other values like quarters ("Q1") may work.
    line: str or int
        The Metro line number
    aspx_data: dict
        The metadata needed for forming a correct form submission.

    Returns
    -------
    An HTML string of the resposnse.
    """
    form_data = {
        "ctl00$ContentPlaceHolder1$rbFYCY": "CY",
        "ctl00$ContentPlaceHolder1$ddlYear": str(year),
        "ctl00$ContentPlaceHolder1$ddlPeriod": str(period),
        "ctl00$ContentPlaceHolder1$btnSubmit": "Submit",
        "ctl00$ContentPlaceHolder1$lbLines": str(line),
        **aspx_data,
    }
    r = requests.post(RIDERSHIP_URL, data=form_data, verify=False)
    r.raise_for_status()
    if r.text.find("Data not available yet") != -1:
        raise ValueError(f"Data not available for {year}, {period}, {line}")

    return r.text


def parse_response(html):
    """
    Parse an HTML response from the ridership form into a dataframe.

    Parameters
    ----------
    html: str
        The HTML webpage from the ridership site.

    Returns
    -------
    A dataframe from the parsed HTML table.
    """
    tables = pd.read_html(
        html,
        flavor="bs4",
        attrs={"id": "ContentPlaceHolder1_ASPxRoundPanel2_gvRidership"},
    )
    if len(tables) == 0:
        raise ValueError("No table found")
    df = tables[0]
    # Filter out the "Total" row
    df = df[df["Day Type"] != "Total"]
    return df


def get_ridership_data(year, period, line, aspx_data):
    """
    Get ridership for a given year, time period, and line.

    Parameters
    ----------
    year: int
        The year for which to fetch the data.
    period: str or int
        The time period in which to fetch the data. Typically you will want
        an integer month, though other values like quarters ("Q1") may work.
    line: str or int
        The Metro line number
    aspx_data: dict
        The metadata needed for forming a correct form submission.

    Returns
    -------
    A dataframe with ridership data for the line/period/year.
    """
    html = submit_form(year, period, line, aspx_data)
    df = parse_response(html)

    df = df.assign(year=year, month=period, line=line)
    return df


def get_all_ridership_data(verbosity=0):
    """
    Fetch all ridership data from the web form.
    """
    lines, years, aspx_data = get_form_data()
    months = [str(i) for i in range(1, 13)]
    ridership = pd.DataFrame()
    # Get the current timestamp so we don't try to fetch from the future.
    now = pd.Timestamp.now()

    for year in years:
        # Don't try to fetch from years in the future.
        if int(year) > now.year:
            continue
        if verbosity > 0:
            print(f"Fetching data for {year}")
        for month in months:
            # Don't try to fetch from months in the future
            if int(year) == now.year and int(month) >= now.month:
                continue
            if verbosity > 1:
                print(f"Fetching data for month {month}")
            for line in lines:
                try:
                    df = get_ridership_data(year, month, line, aspx_data)
                    ridership = ridership.append(df)
                    if verbosity > 2:
                        print(f"Fetched data for line {line}")
                except Exception as e:
                    if verbosity > 2:
                        print(f"Failed to get data for line {line}")
                        print(e)
    return ridership


if __name__ == "__main__":
    today = datetime.date.today()
    name = "metro-ridership-{}".format(today)
    ridership = get_all_ridership_data(3)
    ridership.to_parquet(name + ".parquet")
    ridership.to_parquet(name + ".parquet")


    
    
    
