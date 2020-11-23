from flask import Blueprint, request, current_app
from sqlalchemy import or_
from .models import SiteModel, SiteTypeModel, VisitModel, MediaOnVisitModel
from gncitizen.core.users.models import UserModel
from gncitizen.core.commons.models import MediaModel
import uuid
import datetime
import json

from geojson import FeatureCollection
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from shapely.geometry import asShape
from gncitizen.utils.jwt import get_id_role_if_exists
from gncitizen.utils.media import save_upload_files
from gncitizen.utils.errors import GeonatureApiError
from gncitizen.utils.sqlalchemy import get_geojson_feature, json_resp
from server import db
from flask_jwt_extended import jwt_optional, jwt_required, get_jwt_identity

routes = Blueprint("sites_url", __name__)


@routes.route("/types", methods=["GET"])
@json_resp
def get_types():
    """Get all sites types
        ---
        tags:
          - Sites (External module)
        responses:
          200:
            description: A list of all site types
    """
    try:
        data = []
        for t in SiteTypeModel.query.all():
            data.append(t.type)
        return {"count": len(data), "site_types": data}, 200
    except Exception as e:
        return {"error_message": str(e)}, 400


@routes.route("/<int:pk>", methods=["GET"])
@json_resp
def get_site(pk):
    """Get a site by id
    ---
    tags:
      - Sites (External module)
    parameters:
      - name: pk
        in: path
        type: integer
        required: true
        example: 1
    definitions:
      properties:
        type: dict
        description: site properties
      geometry:
        type: geojson
        description: GeoJson geometry
    responses:
      200:
        description: A site detail
    """
    try:
        site = SiteModel.query.get(pk)
        formatted_site = format_site(site)
        last_visit = VisitModel.query\
            .filter_by(id_site=pk)\
            .order_by(VisitModel.timestamp_update.desc())\
            .first()
        if last_visit is not None:
            formatted_site['properties']['last_visit'] = last_visit.as_dict()
        photos = get_site_photos(pk)
        formatted_site['properties']['photos'] = photos
        return {"features": [formatted_site]}, 200
    except Exception as e:
        return {"error_message": str(e)}, 400


@routes.route("/<int:pk>/jsonschema", methods=["GET"])
@json_resp
def get_site_jsonschema(pk):
    try:
        site = SiteModel.query.get(pk)
        data_dict = site.site_type.custom_form.json_schema
        return data_dict, 200
    except Exception as e:
        return {"error_message": str(e)}, 400


def get_site_photos(site_id):
    photos = db.session.query(
        MediaModel,
        VisitModel,
    ).filter(
        VisitModel.id_site == site_id
    ).join(
        MediaOnVisitModel, MediaOnVisitModel.id_media == MediaModel.id_media
    ).join(
        VisitModel, VisitModel.id_visit == MediaOnVisitModel.id_data_source
    ).all()
    return [{
                'url': '/media/{}'.format(p.MediaModel.filename),
                'date': p.VisitModel.as_dict()['date'],
                'author': p.VisitModel.obs_txt,
            } for p in photos]


def format_site(site, dashboard=False):
    feature = get_geojson_feature(site.geom)
    site_dict = site.as_dict(True)
    for k in site_dict:
        if k not in ("id_role", "geom"):
            feature["properties"][k] = site_dict[k]
    if dashboard:
        feature["properties"]["creator_can_delete"] = site.id_role\
            and VisitModel.query.filter_by(
                id_site=site.id_site).filter(or_(
                VisitModel.id_role!=site.id_role,
                VisitModel.id_role.is_(None))).count() == 0
    return feature


def prepare_sites(sites, dashboard=False):
    count = len(sites)
    features = []
    for site in sites:
        formatted = format_site(site, dashboard)
        photos = get_site_photos(site.id_site)
        if len(photos) > 0:
            formatted['properties']['photo'] = photos[0]
        features.append(formatted)
    data = FeatureCollection(features)
    data["count"] = count
    return data


@routes.route("/", methods=["GET"])
@json_resp
def get_sites():
    """Get all sites
    ---
    tags:
      - Sites (External module)
    definitions:
      FeatureCollection:
        properties:
          type: dict
          description: site properties
        geometry:
          type: geojson
          description: GeoJson geometry
    responses:
      200:
        description: List of all sites
    """
    try:
        sites = SiteModel.query.all()
        return prepare_sites(sites)
    except Exception as e:
        return {"error_message": str(e)}, 400


@routes.route("/programs/<int:id>", methods=["GET"])
@json_resp
def get_program_sites(id):
    """Get all sites
    ---
    tags:
      - Sites (External module)
    definitions:
      FeatureCollection:
        properties:
          type: dict
          description: site properties
        geometry:
          type: geojson
          description: GeoJson geometry
    responses:
      200:
        description: List of all sites
    """
    try:
        sites = SiteModel.query.filter_by(id_program=id).all()
        return prepare_sites(sites)
    except Exception as e:
        return {"error_message": str(e)}, 400


@routes.route("/users/<int:user_id>", methods=["GET"])
@json_resp
def get_user_sites(user_id):
    # try:
        created_sites = SiteModel.query.filter_by(
            id_role=user_id).order_by(
            SiteModel.timestamp_create.desc()).all()
        return prepare_sites(created_sites, dashboard=True)
    # except Exception as e:
    #     return {"error_message": str(e)}, 400


@routes.route("/", methods=["POST"])
@json_resp
@jwt_optional
def post_site():
    """Ajout d'un site
    Post a site
        ---
        tags:
          - Sites (External module)
        summary: Creates a new site
        consumes:
          - application/json
        produces:
          - application/json
        parameters:
          - name: body
            in: body
            description: JSON parameters.
            required: true
            schema:
              id: Site
              properties:
                id_program:
                  type: integer
                  description: Program foreign key
                  required: true
                  example: 1
                name:
                  type: string
                  description: Site name
                  default:  none
                  example: "Site 1"
                id_type:
                  type: integer
                  description: must be one of the supported site types' id
                  required: True
                  example: 1
                geometry:
                  type: string
                  example: {"type":"Point", "coordinates":[5,45]}
        responses:
          200:
            description: Site created
        """
    try:
        request_data = dict(request.get_json())

        datas2db = {}
        for field in request_data:
            if hasattr(SiteModel, field):
                datas2db[field] = request_data[field]
        current_app.logger.debug("datas2db: %s", datas2db)
        try:
            newsite = SiteModel(**datas2db)
        except Exception as e:
            current_app.logger.debug(e)
            raise GeonatureApiError(e)

        try:
            shape = asShape(request_data["geometry"])
            newsite.geom = from_shape(Point(shape), srid=4326)
        except Exception as e:
            current_app.logger.debug(e)
            raise GeonatureApiError(e)

        id_role = get_id_role_if_exists()
        if id_role is not None:
            newsite.id_role = id_role
            role = UserModel.query.get(id_role)
            newsite.obs_txt = role.username
            newsite.email = role.email
        else:
            if newsite.obs_txt is None or len(newsite.obs_txt) == 0:
                newsite.obs_txt = "Anonyme"

        newsite.uuid_sinp = uuid.uuid4()

        db.session.add(newsite)
        db.session.commit()
        # Réponse en retour
        result = SiteModel.query.get(newsite.id_site)
        return {
                   "message": "New site created.",
                   "features": [format_site(result)]
               }, 200
    except Exception as e:
        current_app.logger.warning("Error: %s", str(e))
        return {"error_message": str(e)}, 400


@routes.route("/", methods=["PATCH"])
@json_resp
@jwt_required
def update_site():
    try:
        update_data = dict(request.get_json())
        update_site = {}
        for prop in ["name", "id_type"]:
            update_site[prop] = update_data[prop]
        try:
            shape = asShape(update_data["geometry"])
            update_site["geom"] = from_shape(Point(shape), srid=4326)
        except Exception as e:
            current_app.logger.warning("[update_site] coords ", e)
            raise GeonatureApiError(e)

        try:
            json_data = update_data.get("json_data")
            if json_data is not None:
                update_site["json_data"] = json.loads(json_data)
        except Exception as e:
            current_app.logger.warning("[update_site] json_data ", e)
            raise GeonatureApiError(e)

        SiteModel.query.filter_by(id_site=update_data.get(
            'id_site')).update(update_site, synchronize_session='fetch')

        db.session.commit()

        return ('site updated successfully'), 200
    except Exception as e:
        current_app.logger.critical("[update_site] Error: %s", str(e))
        return {"message": str(e)}, 400


@routes.route("/<int:site_id>/visits", methods=["POST"])
@json_resp
@jwt_optional
def post_visit(site_id):
    try:
        request_data = request.get_json()

        new_visit = VisitModel(
            id_site=site_id,
            date=request_data['date'],
            json_data=request_data['data']
        )

        id_role = get_id_role_if_exists()
        if id_role is not None:
            new_visit.id_role = id_role
            role = UserModel.query.get(id_role)
            new_visit.obs_txt = role.username
            new_visit.email = role.email
        else:
            if new_visit.obs_txt is None or len(new_visit.obs_txt) == 0:
                new_visit.obs_txt = "Anonyme"

        db.session.add(new_visit)
        db.session.commit()

        # Réponse en retour
        result = VisitModel.query.get(new_visit.id_visit)
        return {
                   "message": "New visit created.",
                   "features": [result.as_dict()]
               }, 200
    except Exception as e:
        current_app.logger.warning("Error: %s", str(e))
        return {"error_message": str(e)}, 400


@routes.route("/<int:site_id>/visits/<int:visit_id>/photos", methods=["POST"])
@json_resp
@jwt_optional
def post_photo(site_id, visit_id):
    try:
        current_app.logger.debug("UPLOAD FILE? " + str(request.files))
        if request.files:
            files = save_upload_files(
                request.files,
                "mares",
                site_id,
                visit_id,
                MediaOnVisitModel,
            )
            current_app.logger.debug("UPLOAD FILE {}".format(files))
            return files, 200
        return [], 200
    except Exception as e:
        current_app.logger.warning("Error: %s", str(e))
        return {"error_message": str(e)}, 400


@routes.route("/<int:site_id>", methods=["DELETE"])
@json_resp
@jwt_required
def delete_observation(site_id):
    current_user = get_jwt_identity()
    try:
        site = db.session.query(SiteModel, UserModel).filter(
            SiteModel.id_site == site_id).join(UserModel, SiteModel.id_role == UserModel.id_user, full=True).first()
        if (current_user == site.UserModel.email):
            SiteModel.query.filter_by(id_site=site_id).delete()
            db.session.commit()
            return ('Site deleted successfully'), 200
        else:
            return ('delete unauthorized'), 403
    except Exception as e:
        return {"message": str(e)}, 500
