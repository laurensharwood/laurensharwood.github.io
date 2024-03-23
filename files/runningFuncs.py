## conda activate running



import os, sys
import pandas as pd
import datetime
import gpxpy
import tcxreader 
from tcxreader.tcxreader import TCXReader, TCXTrackPoint
import garminconnect
#conda install -c conda-forge matplotlib
import matplotlib as mpl
import folium
from folium import plugins
from datetime import datetime
from IPython.core.display import display, HTML
import numpy as np
import plotly 
import plotly.express as px
import seaborn as sns
import calplot
from datetime import timedelta

def correct_time(in_fi, date_col):
    runs = pd.read_csv(in_fi)
    runs['PST'] = runs[date_col].astype('datetime64[ns]') - timedelta(hours=6)
    runs.to_csv(in_fi)


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
    new_bike_file = os.path.join(data_dir,'bikeTCX_'+date+'.csv') 
    ##new_bike_file['PST'] = new_bike_file['date'].astype('datetime64[ns]') - timedelta(hours=6)
    df_bike.to_csv(new_bike_file)
    
    print(df)
    df.set_index('file', inplace=True)
    df['name'] = [os.path.basename(f) for f in df.index]
    df['miles'] = [f/1609.34 for f in df['distance']]
    df['seconds'] = df['duration']
    df['minutes'] = [f/60 for f in df['seconds']]
    df['meters'] = df['distance']
    df['avg_mph'] = df['miles']/df['minutes']*60
    df['min_per_mi'] = df['minutes']/df['miles']
    df['PST'] = df['date'].astype('datetime64[ns]' ) - timedelta(hours=8) ## all_garmin_points 
    df['cad_avg'] = [float(str(i).split(":")[-1].replace("}", "").replace(" ", "")) for i in df.cadence]
    cad_max = []
    for i in df['cadence']:
        if len(str(i).split(": ")) == 4:
            cad_max.append(int(str(i).split(": ")[-3].split(", ")[0]))
        else:
            cad_max.append(0)
    df['cad_max'] = cad_max
    df_sort = df.sort_values('date').dropna()
    new_running_file = os.path.join(data_dir,'runTCX_'+date+'.csv')
    df_sort['PST'] = df_sort['date'].astype('datetime64[ns]') - timedelta(hours=6)
    df_sort.to_csv(new_running_file)
    return new_running_file, new_bike_file

def parsingGPX(data_dir):
    all_df = pd.DataFrame(columns=['file', 'lat', 'lon', 'ele', 'speed', 'time'])
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
                    all_df.loc[len(all_df.index)] = [fi, pt.latitude, pt.longitude, pt.elevation, speed, pt.time]
    all_df.to_csv(os.path.join(data_dir, "all_garmin_points.csv"))

def cal_heatmap(fileName, columnName):
    df = pd.read_csv(fileName)

    df = df[df.ascent < 15000]
    df = df.sort_values('date')
    df['index'] = np.arange(len(df))
    df['PST'] = df['date'].astype('datetime64[ns]') - timedelta(hours=6)
    dates = df.PST.to_list()
    
    df['dist_mi'] = [float(0.000621)*float(i) for i in df.distance.to_list()]
    df['dur_min'] = [float(i)/float(60) for i in df.duration.to_list()]
    df['mph'] = df['dist_mi']/(df['dur_min']/60)
    df['ascent_ft'] = [float(i)*float(3.28084) for i in df.ascent.to_list()]
    df = df[df.mph < 13]
    df = df[df.mph > 1]
    
    
    # Create a column containing the month
    df['month'] = pd.to_datetime(df['PST']).dt.to_period('M')
    df['week'] = pd.to_datetime(df['PST']).dt.to_period('W')
    
    df['cad_avg'] = [float(str(i).split(":")[3].replace("}", "").replace(" ", "")) for i in df.cadence]
    df['cad_max'] =  [int(str(i).split(":")[2].split(", ")[0].replace(" ", "")) for i in df.cadence]
    
    df = df.reindex(sorted(df.columns), axis=1)
    df['month_num'] = [int(str(i).split("-")[1]) for i in df.PST]
    df["Month"] = df.month_num.map({1:"January", 2:"February", 3:"March", 4:"April",  5:"May", 6:"June", 7:"July", 8:"August", 9:"September", 10:"October", 11:"November", 12:"December"})
    df['Year'] = [int(str(i).split("-")[0]) for i in df.PST]
    df["Day"] = [int(str(i).split("-")[2].split(" ")[0]) for i in df.PST]

    events = pd.Series([i for i in df[columnName]], 
                       index=[i for i in df['PST'].astype('datetime64[ns]')])
    calplot.calplot(events, suptitle="running "+columnName+" per day", cmap='YlGn', colorbar=True)
    
    


def plot3D(df, out_fi):
    sb_3d = px.scatter_3d(df, x='lon', y='lat', z='ele', color='ele') ##, template='plotly_dark'
    sb_3d.update_traces(marker=dict(size=1.0), selector=dict(mode='markers'))
    sb_3d.show()
    sb_3d.write_html(out_fi)
    
def plot_heatmap(df, out_name):
    df = df.set_index("time").sort_index()
    
    # for routes polylines 
    all_routes_xy = [] 
    for k, v in df.groupby(['file']):
        route_lats = v.lat.to_list()
        route_lons = v.lon.to_list()
        all_routes_xy.append(list(zip(route_lats, route_lons)))
    
    #df = df[start:end].dropna()
    
    heatmap = folium.Map(location=[df.lat[-1], df.lon[-1]],
                         control_scale=False,
                         zoom_start=12)
    
    tile = folium.TileLayer(tiles = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
                            attr = 'ESRI', name = 'ESRI Satellite', overlay = True, control = True, show = True).add_to(heatmap)
    
    cluster = plugins.HeatMap(data=[[la, lo] for la, lo in zip(df.lat, df.lon)],
                              name="heatmap",
                              min_opacity=0.15, max_zoom=10,  radius=5, blur=5)
    heatmap.add_child(cluster)
    
    fg = folium.FeatureGroup("routes")
    folium.PolyLine(locations=all_routes_xy
                    , weight=0.6, opacity = 0.5, color='red', control = True, show = True
                  ).add_to(fg)
    fg.add_to(heatmap)
    
    folium.LayerControl().add_to(heatmap)
    
    heatmap.save(out_name)
    return heatmap