# 
#   Copyright (C) 2017   Free Software Foundation, Inc.
# 
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
# 

# import ogr
# import gosm


class kmlfile(object):
    """Output file in KML format."""
    def open(self, file):
        self.file = open(file, 'w')
        
    def header(self, title):
        self.title = title
        self.file.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        self.file.write('<kml xmlns="http://www.opengis.net/kml/2.2" xmlns:gx="http://www.google.com/kml/ext/2.2" xmlns:kml="http://www.opengis.net/kml/2.2">\n')
        self.file.write('    <Document>\n')
        self.file.write('        <name>' + title + '</name>\n')
        self.file.write('            <visibility>1</visibility>\n')
        self.file.write('            <open>1</open>\n')

    def footer(self):
        self.file.write('    /Document>\n')
        self.file.write('/kml>\n')
        
    def placemark(self, ):
        self.file.write('        <Placemark>\n')
        self.file.write('            <name>' + record['name'] + '</name>\n')
        style = '#fixme'
        way = record['way']
        if type == 'waypoint':
            style = self.wayStyle()
        elif type == 'line':
            color = self.lineColor()
            style = '#line_' + color
            self.file.write('        <LineString>\n')
            self.file.write('            <tessellate>1</tessellate>\n')
            self.file.write('            <altitudeMode>clampToGround</altitudeMode>\n')
            way = ''
            self.file.write(way + '\n')
            self.file.write('        </LineString>\n')
        elif type == 'polygon':
            style = '#Polygon'
            self.file.write('        <Polygon>\n')
            self.file.write('            <extrude>1</extrude>\n')
            self.file.write('            <altitudeMode>relativeToGround</altitudeMode>\n')
            self.file.write(way + '\n')
            self.file.write('        </Polygon>\n')
            self.file.write('        <styleUrl>' + style + '</styleUrl>\n')
            self.file.write('      </Placemark>\n')

    def wayStyle(self):
        print("Unimplemented")

    def lineColor(self):
        print("Unimplemented")

    def description(self):
        print("Unimplemented")
    
    def folderStart(self, folder):
        self.folder = folder
        self.file.write('<Folder>')
        self.file.write('<name>' + folder + '</name>')
        
    def folderEnd(self):
        self.file.write('</Folder>')
        
