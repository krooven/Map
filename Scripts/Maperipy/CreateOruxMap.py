import os.path, datetime
from maperipy import *
import GenIsraelHikingTiles

# http://stackoverflow.com/questions/749711/how-to-get-the-python-exe-location-programmatically
MaperitiveDir = os.path.dirname(os.path.dirname(os.path.normpath(os.__file__)))
# App.log('MaperitiveDir: ' + MaperitiveDir)
ProgramFiles = os.path.normpath(os.path.dirname(MaperitiveDir))
# App.log('ProgramFiles: ' + ProgramFiles)
IsraelHikingDir = os.path.dirname(os.path.dirname(os.path.normpath(App.script_dir)))
# App.log('App.script_dir: ' + App.script_dir)
# App.log('IsraelHikingDir: ' + IsraelHikingDir)
App.run_command('change-dir dir="' + IsraelHikingDir +'"')
os.chdir(IsraelHikingDir)

# Keep the name of the Tile Upload command
upload_tiles = os.path.join(IsraelHikingDir, "Scripts", "Batch", "UploadTiles.bat")

def zip_and_upload(zip_file):
    if os.path.exists(upload_tiles):
        App.log("=== Create a Zip file with new tiles ===")
        App.run_command('zip base-dir="' + os.path.join(IsraelHikingDir, 'Site') + '" zip-file="' + zip_file + '"')
        zip_file_basename = os.path.basename(zip_file)
        App.log("=== Upload " + zip_file_basename + "===")
        App.log('App.start_program("' + upload_tiles + '", [' + zip_file_basename + '])')
        App.start_program(upload_tiles, [zip_file_basename])

gen_cmd =  GenIsraelHikingTiles.IsraelHikingTileGenCommand(BoundingBox(Srid.Wgs84LonLat, 34.00842, 29.32535, 35.92745, 33.398339999), 7, 16)

if          not os.path.exists(os.path.join(IsraelHikingDir, 'output', 'TileUpdate.zip')) \
        and not os.path.exists(os.path.join(IsraelHikingDir, 'output', 'TileUpdate16.zip')) \
        and not os.path.exists(os.path.join(IsraelHikingDir, 'output', 'LastModified.zip')):
    App.log("=== Update israel-and-palestine-latest.osm.pbf ===")
    # wget for Windows: http://gnuwin32.sourceforge.net/packages/wget.htm
    App.run_program(os.path.join(ProgramFiles, 'wget', 'wget.exe'), 1200,
                    ["--timestamping",
                     "--no-directories", "--no-verbose",
                     '--directory-prefix="' + os.path.join(IsraelHikingDir, 'Cache') + '"',
                     "http://download.geofabrik.de/asia/israel-and-palestine-latest.osm.pbf"])
    LastModified = datetime.datetime.fromtimestamp(os.path.getmtime(os.path.join(IsraelHikingDir, 'Cache', 'israel-and-palestine-latest.osm.pbf')))
    if LastModified + datetime.timedelta(1) < datetime.datetime.today():
	    App.log("=== pbf file not updated ===");
	    App.run_command("pause 15000")
    # Create LastModified.js file and add it to zip file
    App.log("=== Create Last Update info:" + LastModified.strftime("%d-%m-%Y") + " ===")
    jsFile = open(os.path.join(IsraelHikingDir, 'Site', 'js', 'LastModified.js'), 'w')
    jsFile.write("function getLastModifiedDate() { return '"
                 + LastModified.strftime("%d-%m-%Y")
                 + "'; }")
    jsFile.close()
    App.run_command('zip base-dir="' + os.path.join(IsraelHikingDir, 'Site') 
        + '" files="' + os.path.join(IsraelHikingDir, 'Site', 'js', 'LastModified.js')
        + '" zip-file="' + os.path.join(IsraelHikingDir, 'output', 'LastModified.zip') + '"')
else :
    App.log('=== Continueing execution of the previous build ===')  
    App.run_command("pause 15000")

zip_file = os.path.join(IsraelHikingDir, 'output', 'TileUpdate.zip')
if not os.path.exists(zip_file) :
    App.run_command("run-script file=" + os.path.join("Scripts", "Maperitive", "IsraelHiking.mscript"))
    # Map Created
    #Original# App.run_command("generate-tiles minzoom=7 maxzoom=15 subpixel=3 tilesdir=" + IsraelHikingDir + "\Site\Tiles use-fprint=true")
    gen_cmd.GenToDirectory(7, 15, os.path.join(IsraelHikingDir, 'Site', 'Tiles'))
    App.collect_garbage()

    program_line = os.path.join(ProgramFiles, "Mobile Atlas Creator", "Create Israel Hiking.bat")
    if os.path.exists(program_line):
        App.log("=== Launch creation of Oruxmap IsraelHiking map ===")
        App.log('App.start_program("' + program_line + '", [])')
        App.start_program(program_line, [])
    zip_and_upload(zip_file)
    App.collect_garbage()

zip_file = os.path.join(IsraelHikingDir, 'output', 'OverlayTiles.zip')
if not os.path.exists(zip_file) :
    App.log("=== Create Trails Overlay tiles ===")
    App.run_command("run-script file=" + os.path.join("Scripts", "Maperitive", "IsraelHikingOverlay.mscript"))
    App.collect_garbage()
    #Original# generate-tiles minzoom=7 maxzoom=16 subpixel=3 min-tile-file-size=385 tilesdir=Site\OverlayTiles use-fprint=true
    gen_cmd.GenToDirectory(7, 16, os.path.join(IsraelHikingDir, 'Site', 'OverlayTiles'))
    App.collect_garbage()
    # zip base-dir=Site zip-file=output\OverlayTiles.zip
    zip_and_upload(zip_file)

    program_line = os.path.join(ProgramFiles, "Mobile Atlas Creator", "All IsraelHikingOverlay Maps.bat")
    if os.path.exists(program_line):
        App.log("=== Launch creation of All IsraelHikingOverlay Maps ===")
        App.log('App.start_program("' + program_line + '", [])')
        App.start_program(program_line, [])
    App.collect_garbage()

zip_file = os.path.join(IsraelHikingDir, 'output', 'TileUpdate16.zip')
if not os.path.exists(zip_file) :
    App.log('=== creating zoom level 16 ===')  
    App.run_command("run-script file=" + os.path.join("Scripts", "Maperitive", "IsraelHiking.mscript"))
    # Map Created
    App.log("=== Create tiles for zoom 16 ===")
    gen_cmd.GenToDirectory(16, 16, os.path.join(IsraelHikingDir, 'Site', 'Tiles'))
    App.collect_garbage()
    zip_and_upload(zip_file)

if          os.path.exists(os.path.join(IsraelHikingDir, 'output', 'TileUpdate.zip')) \
        and os.path.exists(os.path.join(IsraelHikingDir, 'output', 'TileUpdate16.zip')) \
        and os.path.exists(os.path.join(IsraelHikingDir, 'output', 'LastModified.zip')):
    # All zip files were created
    if os.path.exists(upload_tiles):
        App.log("=== Upload Last Update info ===")
        App.log('App.start_program("' + upload_tiles + '", ["LastModified.zip"])')
        App.start_program(upload_tiles, ["LastModified.zip"])

App.collect_garbage()
os.chdir(MaperitiveDir)

# vim: shiftwidth=4 expandtab