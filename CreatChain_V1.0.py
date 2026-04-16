"""
Title: Create new Chainage Point
Project: IDDP (Orange Gate) 
Description: 
    Automatically creates new chainage points and splits the selected polygon feature classes.
"""
import arcpy
import math
import datetime
import os

arcpy.env.overwriteOutput = True

def get_extended_point(poly_geometry, side, distance_m):
    vertices = []
    for part in poly_geometry:
        for pnt in part:
            if pnt: vertices.append(pnt)
    
    if len(vertices) < 3: return None

    tr_idx = 0
    tl_idx = 0
    max_tr = -float('inf')
    max_tl = -float('inf')

    for i, p in enumerate(vertices):
        if (p.X + p.Y) > max_tr:
            max_tr = p.X + p.Y
            tr_idx = i
        if (p.Y - p.X) > max_tl:
            max_tl = p.Y - p.X
            tl_idx = i
            
    p_tr = vertices[tr_idx] 
    p_tl = vertices[tl_idx] 
    
    if side.upper() == "RIGHT":
        base_pnt = p_tr
        ref_pnt = p_tl
    else:
        base_pnt = p_tl
        ref_pnt = p_tr

    dx = base_pnt.X - ref_pnt.X
    dy = base_pnt.Y - ref_pnt.Y
    angle = math.atan2(dy, dx)

    new_x = base_pnt.X + (distance_m * math.cos(angle))
    new_y = base_pnt.Y + (distance_m * math.sin(angle))
    
    return arcpy.Point(new_x, new_y)

def split_in_place(poly_layer, interval):

    arcpy.env.outputZFlag = "Disabled"
    arcpy.env.outputMFlag = "Disabled"

    desc = arcpy.Describe(poly_layer)
    workspace = desc.path

    desc_ws = arcpy.Describe(workspace)
    if hasattr(desc_ws, "dataType") and desc_ws.dataType == "FeatureDataset":
        workspace = desc_ws.path

    has_z = desc.hasZ
    spatial_ref = desc.spatialReference
    
    field_list = [f.name for f in arcpy.ListFields(poly_layer) 
                  if f.type not in ("OID", "Geometry") and 
                  f.name.lower() not in ("shape_length", "shape_area", "globalid")]
    
    cursor_fields = ["SHAPE@"] + field_list

    edit = arcpy.da.Editor(workspace)
    edit.startEditing(False, True)
    edit.startOperation()

    try:
        new_features = []

        with arcpy.da.SearchCursor(poly_layer, cursor_fields) as cursor:
            for row in cursor:
                geom = row[0]
                attributes = list(row[1:])
                if geom is None:
                    continue
                part = geom.getPart(0)
                if len(part) < 2:
                    continue

                p1 = part[0]
                p2 = part[1]

                dx = p2.X - p1.X
                dy = p2.Y - p1.Y

                angle = math.atan2(dy, dx)

                perp_angle = angle + math.pi / 2
                dx_cut = math.cos(perp_angle)
                dy_cut = math.sin(perp_angle)

                if dy_cut < 0:
                    dx_cut = -dx_cut
                    dy_cut = -dy_cut
                center = geom.centroid

                distances = []
                for part in geom:
                    for p in part:
                        if p:
                            d = ((p.X - center.X) * dx_cut +
                                 (p.Y - center.Y) * dy_cut)
                            distances.append(d)

                if not distances:
                    continue

                min_d = min(distances)
                max_d = max(distances)

                remaining_poly = geom
                current_d = max_d - interval   

                while current_d > min_d:

                    length = 10000

                    cx = center.X + dx_cut * current_d
                    cy = center.Y + dy_cut * current_d

                    dx_line = -dy_cut
                    dy_line = dx_cut

                    x1 = cx + dx_line * length
                    y1 = cy + dy_line * length

                    x2 = cx - dx_line * length
                    y2 = cy - dy_line * length

                    if has_z:
                        pnt1 = arcpy.Point(x1, y1, 0)
                        pnt2 = arcpy.Point(x2, y2, 0)
                    else:
                        pnt1 = arcpy.Point(x1, y1)
                        pnt2 = arcpy.Point(x2, y2)

                    cut_line = arcpy.Polyline(
                        arcpy.Array([pnt1, pnt2]),
                        spatial_ref,
                        has_z,
                        False
                    )

                    try:
                        cut_result = remaining_poly.cut(cut_line)
                    except:
                        current_d -= interval
                        continue

                    if not cut_result or len(cut_result) < 2:
                        current_d -= interval
                        continue

                    part1, part2 = cut_result

                    def proj(pt):
                        return ((pt.X - center.X) * dx_cut +
                                (pt.Y - center.Y) * dy_cut)

                    if proj(part1.centroid) > proj(part2.centroid):
                        slice_part = part1
                        remaining_poly = part2
                    else:
                        slice_part = part2
                        remaining_poly = part1

                    new_features.append([slice_part] + attributes)

                    current_d -= interval

                new_features.append([remaining_poly] + attributes)

        with arcpy.da.UpdateCursor(poly_layer, ["SHAPE@"]) as up_cursor:
            for row in up_cursor:
                up_cursor.deleteRow()

        with arcpy.da.InsertCursor(poly_layer, cursor_fields) as in_cursor:
            for poly in new_features:
                in_cursor.insertRow(poly)

        edit.stopOperation()
        edit.stopEditing(True)

        arcpy.AddMessage("✅ Successfully split features (Top → Bottom).")

    except Exception as e:
        if edit.isEditing:
            edit.abortOperation()
            edit.stopEditing(False)

        arcpy.AddError("Error: " + str(e))

if __name__ == "__main__":
    input_layer = arcpy.GetParameterAsText(0)   
    output_point_fc = arcpy.GetParameterAsText(1)   
    side = arcpy.GetParameterAsText(2) 
    split_interval = float(arcpy.GetParameterAsText(3))  
    extension_dist = 4 
    try:
        desc = arcpy.Describe(input_layer)
        if not desc.fidSet:
            arcpy.AddError("Please select at least one polygon feature.")
        else:
            arcpy.AddMessage("Creating extended point...")
            spatial_ref = desc.spatialReference
            if arcpy.Exists(output_point_fc):
                arcpy.AddMessage(f"Found existing FC: {output_point_fc}. Adding point...")

                with arcpy.da.InsertCursor(output_point_fc, ["SHAPE@"]) as i_cursor:
                    with arcpy.da.SearchCursor(input_layer, ["SHAPE@"]) as s_cursor:
                        for row in s_cursor:
                            new_pnt = get_extended_point(row[0], side, extension_dist)
                            if new_pnt:
                                pnt_geom = arcpy.PointGeometry(new_pnt, spatial_ref)
                                i_cursor.insertRow([pnt_geom])
                
                arcpy.AddMessage("Point added successfully.")
            else:
                arcpy.AddError("Output Feature Class Not Found.")
            
            arcpy.AddMessage("Splitting features...")
            split_in_place(input_layer, split_interval)

    except Exception as e:
        arcpy.AddError(f"Error: {str(e)}")