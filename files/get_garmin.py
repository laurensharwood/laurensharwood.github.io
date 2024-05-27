#!/usr/bin/env python3
"""
in terminal: 
export EMAIL=your garmin username/email 
export PASSWORD=your garmin pwd
"""
import os, sys
import shutil
import numpy as np
import pandas as pd
import datetime
from datetime import datetime, timedelta, date, timezone
import json
import logging
from getpass import getpass
from enum import Enum, auto
from typing import Any, Dict, List, Optional
from withings_sync import fit
import readchar
import requests
import garth
from garth.exc import GarthHTTPError
import gpxpy
import tcxreader 
from tcxreader.tcxreader import TCXReader, TCXTrackPoint

import matplotlib
from matplotlib import pyplot
import folium
from folium import plugins
from IPython.display import display, HTML
import plotly 
import plotly.express as px
import seaborn as sns

import calplot

import schedule 

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class Garmin:
    """
    from https://github.com/cyberjunky/python-garminconnect/blob/master/garminconnect/__init__.py
    Class for fetching data from Garmin Connect.
    """

    def __init__(
        self, email=None, password=None, is_cn=False, prompt_mfa=None
    ):
        """Create a new class instance."""
        self.username = email
        self.password = password
        self.is_cn = is_cn
        self.prompt_mfa = prompt_mfa
        self.garmin_connect_activities = ("/activitylist-service/activities/search/activities")
        self.garmin_connect_activity = "/activity-service/activity"
        self.garmin_connect_activity_types = ("/activity-service/activity/activityTypes" )
        self.garmin_connect_fit_download = "/download-service/files/activity"
        self.garmin_connect_tcx_download = ("/download-service/export/tcx/activity")
        self.garmin_connect_gpx_download = ("/download-service/export/gpx/activity")
        self.garmin_connect_kml_download = ("/download-service/export/kml/activity")
        self.garmin_connect_csv_download = ("/download-service/export/csv/activity")
        self.garmin_workouts = "/workout-service"
        self.garth = garth.Client(domain="garmin.cn" if is_cn else "garmin.com")

        self.display_name = None
        self.full_name = None
        self.unit_system = None

    def connectapi(self, path, **kwargs):
        return self.garth.connectapi(path, **kwargs)

    def download(self, path, **kwargs):
        return self.garth.download(path, **kwargs)

    def login(self, /, tokenstore: Optional[str] = None):
        """Log in using Garth."""
        tokenstore = tokenstore or os.getenv("GARMINTOKENS")

        if tokenstore:
            if len(tokenstore) > 512:
                self.garth.loads(tokenstore)
            else:
                self.garth.load(tokenstore)
        else:
            self.garth.login(
                self.username, self.password, prompt_mfa=self.prompt_mfa
            )

        self.display_name = self.garth.profile["displayName"]
        self.full_name = self.garth.profile["fullName"]

        return True


    def get_activities_by_date(self, startdate, enddate, activitytype=None):
        """
        Fetch available activities between specific dates
        :param startdate: String in the format YYYY-MM-DD
        :param enddate: String in the format YYYY-MM-DD
        :param activitytype: (Optional) Type of activity you are searching
                             Possible values are [cycling, biking]
        :return: list of JSON activities
        """

        activities = []
        start = 0
        limit = 20
        # mimicking the behavior of the web interface that fetches
        # 20 activities at a time
        # and automatically loads more on scroll
        url = self.garmin_connect_activities
        params = {
            "startDate": str(startdate),
            "endDate": str(enddate),
            "start": str(start),
            "limit": str(limit),
        }
        if activitytype:
            params["activityType"] = str(activitytype)

        logger.debug(
            f"Requesting activities by date from {startdate} to {enddate}"
        )
        while True:
            params["start"] = str(start)
            logger.debug(f"Requesting activities {start} to {start+limit}")
            act = self.connectapi(url, params=params)
            if act:
                activities.extend(act)
                start = start + limit
            else:
                break

        return activities

    class ActivityDownloadFormat(Enum):
        """Activity variables."""

        ORIGINAL = auto()
        TCX = auto()
        GPX = auto()
        KML = auto()
        CSV = auto()

    def download_activity(
        self, activity_id, dl_fmt=ActivityDownloadFormat.TCX
    ):
        """
        Downloads activity in requested format and returns the raw bytes. For
        "Original" will return the zip file content, up to user to extract it.
        "CSV" will return a csv of the splits.
        """
        activity_id = str(activity_id)
        urls = {
            Garmin.ActivityDownloadFormat.ORIGINAL: f"{self.garmin_connect_fit_download}/{activity_id}",  # noqa
            Garmin.ActivityDownloadFormat.TCX: f"{self.garmin_connect_tcx_download}/{activity_id}",  # noqa
            Garmin.ActivityDownloadFormat.GPX: f"{self.garmin_connect_gpx_download}/{activity_id}",  # noqa
            Garmin.ActivityDownloadFormat.KML: f"{self.garmin_connect_kml_download}/{activity_id}",  # noqa
            Garmin.ActivityDownloadFormat.CSV: f"{self.garmin_connect_csv_download}/{activity_id}",  # noqa
        }
        if dl_fmt not in urls:
            raise ValueError(f"Unexpected value {dl_fmt} for dl_fmt")
        url = urls[dl_fmt]

        logger.debug("Downloading activities from %s", url)

        return self.download(url)

class GarminConnectConnectionError(Exception):
    """Raised when communication ended in error."""

class GarminConnectTooManyRequestsError(Exception):
    """Raised when rate limit is exceeded."""

class GarminConnectAuthenticationError(Exception):
    """Raised when authentication is failed."""

class GarminConnectInvalidFileFormatError(Exception):
    """Raised when an invalid file format is passed to upload."""

def display_json(api_call, output):
    """Format API output for better readability."""

    dashed = "-" * 20
    header = f"{dashed} {api_call} {dashed}"
    footer = "-" * len(header)

    print(header)

    if isinstance(output, (int, str, dict, list)):
        print(json.dumps(output, indent=4))
    else:
        print(output)

    print(footer)

def display_text(output):
    """Format API output for better readability."""
    dashed = "-" * 60
    header = f"{dashed}"
    footer = "-" * len(header)

def get_credentials():
    """Get user credentials."""

    email = input("Login e-mail: ")
    password = getpass("Enter password: ")

    return email, password


def init_api(email, password, tokenstore):
    """Initialize Garmin API with your credentials."""
    try:
        print(
            f"Trying to login to Garmin Connect using token data from ...\n'{tokenstore}'"
        )
        garmin = Garmin()
        garmin.login(tokenstore)
    except (FileNotFoundError, GarthHTTPError, GarminConnectAuthenticationError):
        # Session is expired. You'll need to log in again
        print(
            "Login tokens not present, login with your Garmin Connect credentials to generate them.\n"
            f"They will be stored in '{tokenstore}' for future use.\n"
        )
        try:
            # Ask for credentials if not set as environment variables
            if not email or not password:
                email, password = get_credentials()

            garmin = Garmin(email, password)
            garmin.login()
            # Save tokens for next login
            garmin.garth.dump(tokenstore)

        except (FileNotFoundError, GarthHTTPError, GarminConnectAuthenticationError, requests.exceptions.HTTPError) as err:
            logger.error(err)
            return None

    return garmin

######################################################################

def switch(api, option, out_dir, startdate, today):
    """Run selected API call."""

    if api:
        activitytype=""
        activities = api.get_activities_by_date(startdate.isoformat(), today.isoformat(), activitytype )
        for activity in activities:
            activity_id = activity["activityId"]
            activity_name = activity["activityName"]
            activity_start = activity["startTimeLocal"].replace(" ", "", -1).replace(":", "", -1).replace("-", "", -1)            
            if option==".gpx":
                gpx_data = api.download_activity( activity_id, dl_fmt=api.ActivityDownloadFormat.GPX)
                with open(os.path.join(out_dir, f"{str(activity_start)}.gpx"), "wb") as fb:
                    fb.write(gpx_data)
            elif option==".tcx":
                tcx_data = api.download_activity(activity_id, dl_fmt=api.ActivityDownloadFormat.TCX)
                with open(os.path.join(out_dir, f"{str(activity_start)}.tcx"), "wb") as fb:
                    fb.write(tcx_data)
            elif option==".zip":
                zip_data = api.download_activity(activity_id, dl_fmt=api.ActivityDownloadFormat.ORIGINAL)
                with open(os.path.join(out_dir, f"{str(activity_start)}.zip"), "wb") as fb:
                    fb.write(zip_data)
            elif option== ".csv":
                csv_data = api.download_activity(activity_id, dl_fmt=api.ActivityDownloadFormat.CSV)
                with open(os.path.join(out_dir, f"{str(activity_start)}.csv"), "wb") as fb:
                    fb.write(csv_data)

######################################################################

def parseTCX(data_dir):
    ''' 
    parse all TCX files in data directory -- make directory name the date of last activity -- writes csv with that date 
    function is quick so okay to reparse TCX files -- for next run, add new files to folder
    '''
    date = os.path.basename(data_dir)
    tcx_files = [i for i in sorted(os.listdir(data_dir)) if i.endswith(".tcx")]
    
    df = pd.DataFrame(columns=['file','date', 'duration',  'distance', 'ascent', 'hr_max', 'cadence', 'avg_speed'])
    df_bike = pd.DataFrame(columns=['file','date', 'duration',  'distance', 'ascent', 'hr_max',  'avg_speed'])
    for tf in tcx_files:
        xy_per_run = []
        file = open(os.path.join(data_dir, tf), 'r')
        tcx_reader = TCXReader()
        TCXTrackPoint = tcx_reader.read(file)
        if TCXTrackPoint.activity_type == "Running":
            df.loc[len(df.index)] = [file.name, TCXTrackPoint.start_time, TCXTrackPoint.duration, TCXTrackPoint.distance, TCXTrackPoint.ascent, TCXTrackPoint.hr_max, TCXTrackPoint.tpx_ext_stats.get('RunCadence'), TCXTrackPoint.avg_speed]
        elif TCXTrackPoint.activity_type == "Biking":
            df_bike.loc[len(df_bike.index)] = [file.name, TCXTrackPoint.start_time, TCXTrackPoint.duration, TCXTrackPoint.distance, TCXTrackPoint.ascent, TCXTrackPoint.hr_max,  TCXTrackPoint.avg_speed]
    
    # df = df[df['avg_speed'] < 15]
    # ## take out biking activities accidentally loged as running where mph is > 12 (5 min mile) 
    # if len(df_bike) > 0:
    #     df_bike=pd.concat([df_bike, df[df['avg_speed'] >= 15]])
    #     df_bike['PST'] = df_bike['date'].astype('datetime64[ns]') - timedelta(hours=6)
    #     df_bike.sort_values('date').dropna().to_csv(os.path.join(data_dir,'bikeTCX_'+date+'.csv') )
    
    ## clean running activity attributes
    df['file'] = [os.path.basename(i) for i in df['file']]
    df.set_index('file', inplace=True)
    df['name'] = [os.path.basename(f) for f in df.index]
    df['miles'] = [f/1609.34 for f in df['distance']]
    df['seconds'] = df['duration']
    df['minutes'] = [f/60 for f in df['seconds']]
    df['meters'] = df['distance']
    df['avg_mph'] = df['miles']/df['minutes']*60
    df['min_per_mi'] = df['minutes']/df['miles']
    df['cad_avg'] = [str(i).split(":")[-1].replace("}", "").replace(" ", "") for i in df.cadence]
    df['cad_max'] = [int(str(i).split(": ")[-3].split(", ")[0]) if len(str(i).split(": ")) == 4 else 0 for i in df['cadence']]
    df['PST'] = df['date'].astype('datetime64[ns]') - timedelta(hours=6)
    
    df.sort_values('PST').dropna().to_csv(os.path.join(data_dir,'runTCX_'+date+'.csv'))
    df['PST']=[str(i) for i in df['PST']]

    return df, df_bike

def parseGPX(data_dir):
    date = os.path.basename(data_dir)
    pts_df = pd.DataFrame(columns=['file', 'lat', 'lon', 'ele', 'speed', 'time'])
    gpx_files = [i for i in sorted(os.listdir(data_dir)) if i.endswith(".gpx")]
    for fi in gpx_files:
        gpx_file = open(os.path.join(data_dir, fi), 'r')
        gpx = gpxpy.parse(gpx_file,version="1.1")
        for track in gpx.tracks:
            for seg in track.segments:
                for point_no, pt in enumerate(seg.points):
                    if pt.speed != None:
                        speed = pt
                    elif point_no > 0:
                        speed = pt.speed_between(seg.points[point_no - 1])
                    elif point_no == 0:
                        speed = 0     
                    pts_df.loc[len(pts_df.index)] = [fi, pt.latitude, pt.longitude, pt.elevation, speed, pt.time]

    pts_df['PST'] = pts_df['time'] - timedelta(hours=6)
    pts_df['PST']=[str(i).split("+")[0] for i in pts_df['PST']]
    pts_df.set_index('file', inplace=True)
    new_pt_csv = os.path.join(data_dir, "allGPX_"+date+".csv")
    pts_df.to_csv(new_pt_csv)
    return pts_df, new_pt_csv

######################################################################

def plot3D(df, out_fi):
    df = df.iloc[::1, :] ## subset every 1 points to keep file size down
    sb_3d = px.scatter_3d(df, x='lon', y='lat', z='ele', color='ele') 
    sb_3d.update_traces(marker=dict(size=2.0), selector=dict(mode='markers'))
 #   sb_3d.show()
    sb_3d.write_html(out_fi)

def plot_heatmap(df, out_name):
    #df = df.set_index("time").sort_index()
    df = df.iloc[::1, :] ## subset every 1 points to keep file size down
    # for routes polylines 
    all_routes_xy = [] 
    for k, v in df.groupby(['file']):
        route_lats = v.lat.to_list()
        route_lons = v.lon.to_list()

        all_routes_xy.append(list(zip(route_lats, route_lons)))
    
    #df = df[start:end].dropna()
    heatmap = folium.Map(location=[np.mean(df.lat), np.mean(df.lon)],
                         control_scale=False,
                         zoom_start=12)
    
    tile = folium.TileLayer(tiles = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
                            attr = 'ESRI', name = 'ESRI Satellite', overlay = True, control = True, show = True).add_to(heatmap)
    
    cluster = plugins.HeatMap(data=[[la, lo] for la, lo in zip(df.lat, df.lon)],
                              name="heatmap",
                              min_opacity=0.15, max_zoom=10,  radius=9, blur=8)
    heatmap.add_child(cluster)
    
    fg = folium.FeatureGroup("routes")
    folium.PolyLine(locations=all_routes_xy
                    , weight=1.0, opacity = 1.0, color='red', control = True, show = True
                  ).add_to(fg)
    fg.add_to(heatmap)
    
    folium.LayerControl().add_to(heatmap)
    
    heatmap.save(out_name)
    return heatmap

def cal_heatmap(df, columnName):

    df = df[df.ascent < 20000]

    df['ascent_ft'] = [float(i)*float(3.28084) for i in df.ascent.to_list()]
    df['ascent_m'] = np.where( df['ascent'] >= 1400, 1400, df['ascent'])

    # Create a column containing the month
    df['month'] = pd.to_datetime(df['PST']).dt.to_period('M')
    df['week'] = pd.to_datetime(df['PST']).dt.to_period('W')

    df = df.reindex(sorted(df.columns), axis=1)
    df['Year'] = [int(str(i).split("-")[0]) for i in df.PST]
    df = df[df['Year'] > 2019]
    df = df[df['Year'] < 2024]
    df = df.sort_values('PST')
    events = pd.Series([i for i in df[columnName]], 
                       index=[i for i in df['PST'].astype('datetime64[ns]')])
    calplot.calplot(events, suptitle="running "+columnName+" per day", cmap='YlOrBr', colorbar=True)
    pyplot.savefig(os.path.join(running_fig_dir, columnName+'_heatCal.png'))


######################################################################
## make sure mac is turned on to run every day at 6:30am
## > crontab -e (to edit/create job)
## Vim (Esc:wq to save): 
## 30 6 * * * Desktop/running_project/get_garmin.py
## > crontab -l (to check)
def main():
    '''
    cd to directory of script / project directory, run script from that directory
    
    '''
    num_days=1 ##sys.argv[1]  
    project_dir=os.path.join("Desktop", "running_project")

    
    file_types=[".tcx", ".gpx", ".csv", ".zip"]

    # Load environment variables if defined
    email = os.getenv("EMAIL")
    password = os.getenv("PASSWORD")
    tokenstore = os.getenv("GARMINTOKENS") or "~/.garminconnect"
    api = None

    today = date.today()
    startdate = today - timedelta(days=num_days)  
    
    YYYYMMDD = today.strftime("%Y%m%d")
    out_dir = os.path.join(project_dir, YYYYMMDD)
    print(f"Saving files in ...\n'{out_dir}'")
    if not os.path.exists(out_dir):
        os.makedirs(out_dir)
        
    archive_dir = os.path.join(project_dir, "archive")
    if not os.path.exists(archive_dir):
        os.makedirs(archive_dir)
    global running_fig_dir
    running_fig_dir = os.path.join(project_dir, "out")
    if not os.path.exists(running_fig_dir):
        os.makedirs(running_fig_dir)        
        
    ## 1) download from garmin
    
    for option in file_types:
        menu_options = {
            option: f"Download activities data by date from '{startdate.isoformat()}' to '{today.isoformat()}'",
            "q": "Exit" }
        if not api:
            api = init_api(email, password, tokenstore)
        if api:
            switch(api, option, out_dir, startdate, today)
        else:
            api = init_api(email, password, tokenstore)    
    if len(os.listdir(out_dir)) == 0:
        os.rmdir(out_dir)

    ## 2) parse gpx, tcx files from the last day, then append onto archive csvs 
    
    runGPX_df, new_pt_csv = parseGPX(out_dir)
    runTCX_df, bikeTCX_df = parseTCX(out_dir)
    ## move each activity file to archive folder 
    for option in file_types:
        move_files = [i for i in os.listdir(out_dir) if (i.endswith(option) and "X_" not in i)]
        for file in move_files:
            os.rename(os.path.join(out_dir, file), os.path.join(archive_dir, file))
    ## merge csvs
    print(archive_dir)
    oldG=os.path.join(archive_dir, "allGPX_archive.csv")
    if os.path.exists(oldG):
        old_GPX = pd.read_csv(oldG, index_col="file")
        Gdf=pd.concat([runGPX_df, old_GPX]).drop_duplicates().sort_values('PST')
        print(Gdf)
        Gdf.to_csv(oldG)
    oldT=os.path.join(archive_dir, "runTCX_archive.csv")
    if os.path.exists(oldT):
        old_TCX = pd.read_csv(oldT, index_col="file")
        Tdf=pd.concat([runTCX_df, old_TCX]).sort_values('PST')
        print(Tdf.drop_duplicates(subset=['PST']))
        Tdf.drop_duplicates(subset=['PST']).to_csv(oldT)
    ## delete directory
    shutil.rmtree(out_dir)

    ## 3) figs
    ## route heatmap
    plot_heatmap(Gdf, os.path.join(running_fig_dir, "heatmap.html"))    
    
    ## 3d routes (set smaller bounds)
    min_lon = -119.98
    max_lon = -119.0
    min_lat = 34.3
    max_lat = 34.5
    df = Gdf[(Gdf['lat'] > min_lat) & (Gdf['lat'] < max_lat) & (Gdf['lon'] > min_lon) & (Gdf['lon'] < max_lon)]
    plot3D(df, os.path.join(running_fig_dir, "route3d.html"))    

    ## calendar heatmap
    cal_heatmap(Tdf, "miles")
    cal_heatmap(Tdf, "ascent_m")
    
if __name__ == '__main__':
    main()    
