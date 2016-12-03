"""Tile generation restriction by an Osm Change file and a polygon.

Read a compressed or uncompressed Osm Change file
Analyze the tiles that were modified at a given range of zoom levels.
Potentially perform the analysis on additional Osm Change files.
Restrict the tile generation within a polygon to changed tiles and their adjecent tiles.

Inputs for each analysis:
- Osm Change file
- Base and new OSM maps, each as either a pbf file or an existing map layer
"""

# TODO:
# - mark center of rel_bbox for relations using members_bbox?
# - Check the removal of the guardband given the "map.rendering.tiles.rendering-bounds-buffer"
#   settings which "specifies the additional buffer around the tile rendering bounds to prevent 
#   labels being cut off at neighboring tiles. Specified as percentage of value, the default is 10%"

# import string
import math
import os
from datetime import *
from System.IO import TextReader
from maperipy import *
from maperipy.osm import *
from PolygonTileGenCommand import PolygonTileGenCommand
import gzip  # https://bitbucket.org/jdhardy/ironpythonzlib/src/tip/tests/gzip.py
import clr
clr.AddReference('System.Xml')
from System.Xml import *

class OsmChangeTileGenCommand(PolygonTileGenCommand):
    """Analyse an OsmChange file and find all tiles to be updated

    Changed tiles are stored in a dictionary of dictionaries:
    self.changed[zoom][(tile_x, tile_y)]
    Changed tiles are added at max_zoom and propagated to lower zoom levels if needed.

    Tiles to be updated are either changed or adjecant to changed tiles.
    self.guard[zoom][(tile_x, tile_y)] is a cache for the tiles to be updated
    """

    def generation_filter(self, zoom, x, y, width, height):
        # Filter rendering of the map in a super-tile
        generate = False
        # Leverage the guard to check every 3rd row and column inside the super-tile
        # Note: This is for safety. We did not see width or height values larger than 3.
        for tile_x in range(x, x+width, 3) + [x+width-1]:
            for tile_y in range(y, y+width, 3) + [y+width-1]:
                if self.updated(zoom, tile_x, tile_y):
                    generate = True
                    # Exit nested loops
                    break
            else:
                continue
            break
        if self.verbose:
            print "     OsmChangeTileGenCommand - Generating {}x{} super-tile: {}/{}/{}: {}".format(
                    width, height, zoom, x, y, generate)
        return generate

    def save_filter(self, tile):
        # Filter the saving to disk of individual tiles in the super tile
        save = self.updated(tile.zoom, tile.tile_x, tile.tile_y)
        if self.verbose:
            reason = "Changed" if tile in self.changed[zoom] else "Guard band" if save else "Skipped"
            save[reason] += 1
            print "     OsmChangeTileGenCommand - Saving tile: {}/{}/{}: {}".format(
                    tile.zoom, tile.tile_x, tile.tile_y, reason)
        return save

    def osmChangeRead(self, change_file, base_map, new_map):
        """Analyze which tiles require an update by using a change file with base and new maps.
        Allows multiple calls with consecutive change files.

        Impacts on the map:
        - If given a base OSM Layer, it is removed from the map.
        - If given a base pbf file, it is not added to the map.
        - If given a new pbf file, it is added to the map.

        Inputs:
        - File name of the change file
        - Base map: either a name of a pbf file or an OSM Layer
          Used for locating tiles with deleted and changed objects.
        - New map: either a name of a pbf file or an OSM Layer
          Used for locating tiles with new and changed objects.

        Return value: OsmLayer of the new map
        """

        App.collect_garbage()
        if self.changed == None:
            self.changed = {x:{} for x in range(self.min_zoom, self.max_zoom+1)}
        # Initialize the guard zone tiles
        self.guard = None
        if self.verbose:
            print "     Reading change file", change_file, "..."
        osmChange = XmlDocument()
        osmChange.Load(osmChangeReader(change_file))
        for element in osmChange.SelectNodes("./osmChange"):
            self.timestamp = datetime.strptime(
                    element.Attributes.GetNamedItem("timestamp").Value,
                    "%Y-%m-%dT%H:%M:%SZ")
            if not element.HasChildNodes:
                return
        if isinstance(base_map, OsmLayer):
            if self.verbose:
                print "     Base OSM map taken from map layer..."
            baseOsm = base_map.osm
            base_map.visible = False
        else:
            if self.verbose:
                print "     Reading base OSM map from", base_map, "..."
            baseOsm = OsmData.load_pbf_file(base_map)
        App.collect_garbage()
        if isinstance(new_map, OsmLayer):
            if self.verbose:
                print "     New OSM map taken from map layer..."
            newOsm = new_map.osm
            result = new_map
        else:
            if self.verbose:
                print "     Loading new OSM map from", new_map, "..."
            newOsm = Map.add_osm_source(new_map).osm
            result = Map.layers[len(Map.layers)-1]
        if self.verbose:
            print "     Analyzing change file ..."
            sum = {key : 0 for key in ("node", "way", "relation")}
        for element in osmChange.SelectNodes("./osmChange/*/*"):
            action = element.ParentNode.Name  # "delete", "modify", or "create"`
            element_type = element.Name  # "node", "way", or "relation"
            element_id = long(element.Attributes.GetNamedItem("id").Value)
            if self.verbose:
                sum[element_type] += 1
            if False and self.verbose:
                print "     {} {} id={}:".format(action, element_type, element_id)
            try:
                if action in ("delete", "modify"):
                    for bbox in self.bboxes(baseOsm, element_type, element_id):
                            self.mark_bbox(bbox)
                if action in ("create", "modify"):
                    for bbox in self.bboxes(newOsm, element_type, element_id):
                        self.mark_bbox(bbox)
            except KeyError:
                # An element does bot exist in the map,
                # no need to redraw its position
                pass
        if self.verbose:
            print "     Analyzed {} nodes, {} ways, and {} relations.".format(
                    sum["node"], sum["way"], sum["relation"])

    def __init__(self, *args):
        PolygonTileGenCommand.__init__(self)
        self.changed = None
        self.guard = None

    def execute(self):
        if self.changed is None or not self.changed[min(self.changed)]:
            return
        PolygonTileGenCommand.execute(self)

    def deg2num(self, lat, lon, zoom):
        # Adapted from
        # http://wiki.openstreetmap.org/wiki/Slippy_map_tilenames#Lon..2Flat._to_tile_numbers_2
        lat_deg = float(lat)
        lon_deg = float(lon)
        lat_rad = math.radians(lat_deg)
        n = 2.0 ** zoom
        tile_x = int((lon_deg + 180.0) / 360.0 * n)
        tile_y = int((1.0 - math.log(math.tan(lat_rad) + (1 / math.cos(lat_rad))) / math.pi) / 2.0 * n)
        return (tile_x, tile_y)

    def updated(self, zoom, x, y):
        try:
            return (x, y) in self.guard[zoom]
        # Handle rare scenarios through exceptions
        except TypeError:
            if self.changed is None:
                # Analysis was not done
                return True
            elif self.guard is None:
                # Guard is not updated
                self.update_guard()
                return self.updated(zoom, x, y)
            else:
                raise
        except KeyError:
            # Zoom levels during tile generation may differ from analyzed zoom levels
            if zoom > max(self.changed):
                # Look for a tile at zoom == max(self.changed) that covers this tile
                return self.updated(zoom-1, x//2, y//2)
            elif zoom < min(self.changed):
                # Look for a tile at zoom == min(self.changed) that is covered by this tile
                zoom += 1
                x *= 2
                y *= 2
                return (self.updated(zoom, x, y)
                        or self.updated(zoom, x+1, y+1)
                        or self.updated(zoom, x, y+1)
                        or self.updated(zoom, x+1, y))
            else:
                raise

    def new_tile_upwards(self, tile, zoom):
        if zoom > max(self.changed) or self.new_tile(tile, zoom):
            self.new_tile_upwards(tuple(coord//2 for coord in tile), zoom-1)

    def new_tile(self, tile, zoom):
        if zoom not in self.changed or tile in self.changed[zoom]:
            return False
        else:
            self.changed[zoom][tile] = True
            if False and self.verbose:
                print "     New tile {t[0]}, {t[1]} in zoom {z}".format(t=tile, z=zoom)
            return True

    def update_guard(self):
        """If needed, update the cache of tiles to be rendered
        by adding a guard of one tile around each changed tile.
        Avoid adding tiles outside the polygon.
        """
        if self.guard is not None:
            return
        self.guard={}
        tile_checked = {}
        for zoom in sorted(self.changed):
            self.guard[zoom] = {}
            tile_checked[zoom] = {}
            for (x, y) in self.changed[zoom]:
                for x_guard in range(x-1, x+2):
                    for y_guard in range(y-1, y+2):
                        if (x_guard, y_guard) not in tile_checked[zoom]:
                            # Check each tile once
                            tile_checked[zoom][(x_guard, y_guard)] = True
                            if ((zoom == min(self.changed) or (x_guard//2, y_guard//2) in self.guard[zoom-1])
                                    and self.tiles_overlapps_polygon(zoom, x_guard, y_guard, 1, 1)):
                                # Included in guard of lower zoom, if exists, and in the polygon 
                                self.guard[zoom][(x_guard, y_guard)] = True

    def statistics(self):
        self.update_guard()
        sum_changed = 0
        sum_guard = 0
        for zoom in self.changed:
            cur_changed = len(self.changed[zoom])
            cur_guard = len(self.guard[zoom])
            sum_changed += cur_changed
            sum_guard += cur_guard
            print "     zoom {:2} has {:5} changed tiles, {:5} update tiles".format(
                    zoom, cur_changed, cur_guard)
        print "     Total of    {:5} changed tiles, {:5} update tiles".format(
                sum_changed, sum_guard)
        return (sum_changed, sum_guard)

    def mark_bbox(self, bbox):
        # Update all tiles covering the bounding box
        if not self.linear_ring_overlapps_polygon(bbox.polygon.exterior):
            # Ignore changes outside the generation polygon
            return
        (left, top) = self.deg2num(bbox.max_y, bbox.min_x, max(self.changed))
        (right, bottom) = self.deg2num(bbox.min_y, bbox.max_x, max(self.changed))
        if self.visualize:
          # Create a symbol for the Polygon
          self.polygon = PolygonSymbol(
                  "{0}/{1}/{2} ({3}x{4} tiles)".format(
                      max(self.changed), left, top, right-left, bottom-top),
                  Srid.Wgs84LonLat)
          self.polygon.style.pen_width = 2
          self.polygon.style.pen_color = Color("red")
          self.polygon.style.pen_opacity = 0.5
          self.polygon.style.fill_opacity = 0
          # Add the plygon to the layer
          self.layer.add_symbol(self.polygon.add(self.gen_polygon))
        for x in range (left, right+1):
            for y in range(bottom, top+1):
                self.new_tile_upwards((x, y), max(self.changed))

    def rel_members_bbox(self, relation):
        return not (relation.has_tag("type") and relation.get_tag("type") == "multipolygon")

    def bboxes(self, osm_data, element_type, element_id):
        if element_type == "node":
            yield osm_data.node(element_id).location.bounding_box
        elif element_type == "way":
            yield osm_data.get_way_geometry(element_id).bounding_box
        elif element_type == "relation":
            relation = osm_data.relation(element_id) 
            members_bbox = self.rel_members_bbox(relation) # Yield each member's bbox?
            rel_bbox = BoundingBox(Srid.Wgs84LonLat)  # Members bboxes accumulator, if needed
            for member in relation.members:
                member_type = None
                if member.ref_type==OsmReferenceType.NODE and osm_data.has_node(member.ref_id):
                    member_type = "node"
                elif member.ref_type==OsmReferenceType.WAY and osm_data.has_way(member.ref_id):
                    member_type = "way"
                elif member.ref_type==OsmReferenceType.RELATION and osm_data.has_relation(member.ref_id):
                    member_type = "relation"
                for bbox in self.bboxes(osm_data, member_type, member.ref_id):
                    if members_bbox:
                        # Yield each member's bbox
                        yield bbox
                    else:
                        rel_bbox.extend_with(bbox)
                if not members_bbox:
                    # Yield the accumulated bbox of all members
                    yield rel_bbox

class osmChangeReader(TextReader):
    def __init__(self, filename):
        if filename[-3:] == ".gz":
            self.f = gzip.open(filename)
        else:
            self.f = open(filename)
    def Read(self, buffer, index, count):
        chars = self.f.read(count).ToCharArray()
        chars.CopyTo(buffer, index)
        return len(chars)

# vim: set shiftwidth=4 expandtab textwidth=0: