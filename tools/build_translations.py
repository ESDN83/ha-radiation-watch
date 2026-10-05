"""Builds custom_components/radiation_watch/translations/*.json from the tables below.

To add a language: copy one block in TEXT, translate the values, run this script.
(Editing the JSON files directly works too, this script only keeps them consistent.)
"""

import json
from pathlib import Path

TEXT = {
    "en": dict(
        bs="Warning", msg="Message", alert="Alert", ev_warning="Warning", ev_notable="Station notable", ev_clear="All clear",
        n_svc="Send notifications to", n_notable="Also notify when a station is notable", n_clear="Notify the all clear",
        d_n_svc="Notify services, for example notify.mobile_app_phone. Empty: no notifications. The entities and the alert event work either way.",
        d_n_notable="Otherwise only for a warning (notable station upwind).", d_n_clear="When the level goes back to calm.",
        title="Radiation Watch",
        desc="Dose rate stations around your home (German BfS network and European EURDEP), wind based early warning and a map card. Map tiles are downloaded once from OpenStreetMap and then served locally.",
        lat="Latitude", lon="Longitude", near="Near radius", far="Far radius", wind="Weather entity for wind", wfb="Fallback weather entity", scan="Update interval",
        d_lat="Centre of the map, defaults to your Home Assistant location.", d_near="Radius of the near view.",
        d_far="Radius of the far view and of the station search. Stations further away are ignored.",
        d_wind="Provides wind direction and speed (attributes wind_bearing and wind_speed).", d_wfb="Used when the first one has no wind data.",
        abs="Absolute threshold", fac="Factor above median", off="Minimum distance above median", sec="Wind sector", minw="Minimum wind speed", age="Maximum data age",
        d_abs="A station at or above this value is always notable.",
        d_fac="A station is notable when it is above median x factor and above median + minimum distance.",
        d_sec="A notable station within this angle either side of the wind direction raises a warning.",
        d_minw="Below this the wind direction is too unsteady to be used.", d_age="Older measurements are dropped.",
        opt_title="Radiation Watch options", opt_desc="Changing location or radii rebuilds the map images.",
        err_far="The far radius must be larger than the near radius.", ab="Radiation Watch is already set up.",
        st="Stations", ew="Early warning", calm="Calm", notable="Notable", warning="Warning", btn="Regenerate map",
    ),
    "de": dict(
        bs="Warnung", msg="Meldung", alert="Alarm", ev_warning="Warnung", ev_notable="Station auffällig", ev_clear="Entwarnung",
        n_svc="Benachrichtigungen senden an", n_notable="Auch bei auffälliger Station benachrichtigen", n_clear="Entwarnung senden",
        d_n_svc="Notify-Dienste, zum Beispiel notify.mobile_app_handy. Leer: keine Benachrichtigungen. Die Entitäten und das Alarm-Ereignis funktionieren trotzdem.",
        d_n_notable="Sonst nur bei einer Warnung (auffällige Station im Wind).", d_n_clear="Wenn die Stufe wieder auf ruhig fällt.",
        title="Radiation Watch",
        desc="Messstationen der Ortsdosisleistung rund um dein Zuhause (BfS-Messnetz und europäisches EURDEP), Frühwarnung nach Windrichtung und eine Kartenkarte. Die Kartenkacheln werden einmalig von OpenStreetMap geladen und danach lokal ausgeliefert.",
        lat="Breitengrad", lon="Längengrad", near="Radius Nah", far="Radius Weit", wind="Wetter-Entität für den Wind", wfb="Ersatz-Wetter-Entität", scan="Abrufintervall",
        d_lat="Mittelpunkt der Karte, vorbelegt mit dem Standort von Home Assistant.", d_near="Radius der Nah-Ansicht.",
        d_far="Radius der Weit-Ansicht und der Stationssuche. Weiter entfernte Stationen werden ignoriert.",
        d_wind="Liefert Windrichtung und Windgeschwindigkeit (Attribute wind_bearing und wind_speed).", d_wfb="Wird genutzt, wenn die erste keine Winddaten hat.",
        abs="Absolute Schwelle", fac="Faktor über dem Median", off="Mindestabstand über dem Median", sec="Windsektor", minw="Mindestwindgeschwindigkeit", age="Maximales Alter der Daten",
        d_abs="Eine Station ab diesem Wert ist immer auffällig.",
        d_fac="Eine Station ist auffällig, wenn sie über Median mal Faktor und über Median plus Mindestabstand liegt.",
        d_sec="Liegt eine auffällige Station innerhalb dieses Winkels beidseits der Windrichtung, gibt es eine Warnung.",
        d_minw="Darunter ist die Windrichtung zu unstet.", d_age="Ältere Messwerte werden verworfen.",
        opt_title="Radiation Watch Optionen", opt_desc="Eine Änderung von Standort oder Radien erzeugt die Kartenbilder neu.",
        err_far="Der Radius Weit muss größer sein als der Radius Nah.", ab="Radiation Watch ist bereits eingerichtet.",
        st="Stationen", ew="Frühwarnung", calm="Ruhig", notable="Auffällig", warning="Warnung", btn="Karte neu erzeugen",
    ),
    "fr": dict(
        bs="Alerte", msg="Message", alert="Alarme", ev_warning="Alerte", ev_notable="Station remarquable", ev_clear="Fin d'alerte",
        n_svc="Envoyer les notifications à", n_notable="Notifier aussi une station remarquable", n_clear="Notifier la fin d'alerte",
        d_n_svc="Services notify, par exemple notify.mobile_app_telephone. Vide : pas de notifications. Les entités et l'événement fonctionnent quand même.",
        d_n_notable="Sinon uniquement en cas d'alerte (station remarquable au vent).", d_n_clear="Quand le niveau redevient calme.",
        title="Radiation Watch",
        desc="Stations de débit de dose autour de votre domicile (réseau allemand BfS et réseau européen EURDEP), alerte précoce selon le vent et une carte. Les tuiles OpenStreetMap sont téléchargées une seule fois puis servies localement.",
        lat="Latitude", lon="Longitude", near="Rayon proche", far="Rayon lointain", wind="Entité météo pour le vent", wfb="Entité météo de secours", scan="Intervalle de mise à jour",
        d_lat="Centre de la carte, par défaut l'emplacement de Home Assistant.", d_near="Rayon de la vue proche.",
        d_far="Rayon de la vue lointaine et de la recherche des stations. Les stations plus éloignées sont ignorées.",
        d_wind="Fournit la direction et la vitesse du vent (attributs wind_bearing et wind_speed).", d_wfb="Utilisée si la première n'a pas de données de vent.",
        abs="Seuil absolu", fac="Facteur au-dessus de la médiane", off="Écart minimal au-dessus de la médiane", sec="Secteur du vent", minw="Vitesse de vent minimale", age="Âge maximal des données",
        d_abs="Une station à partir de cette valeur est toujours remarquable.",
        d_fac="Une station est remarquable si elle dépasse médiane x facteur et médiane + écart minimal.",
        d_sec="Une station remarquable dans cet angle de part et d'autre de la direction du vent déclenche une alerte.",
        d_minw="En dessous, la direction du vent est trop instable.", d_age="Les mesures plus anciennes sont ignorées.",
        opt_title="Options de Radiation Watch", opt_desc="Modifier l'emplacement ou les rayons régénère les images de la carte.",
        err_far="Le rayon lointain doit être plus grand que le rayon proche.", ab="Radiation Watch est déjà configuré.",
        st="Stations", ew="Alerte précoce", calm="Calme", notable="Remarquable", warning="Alerte", btn="Régénérer la carte",
    ),
    "es": dict(
        bs="Alerta", msg="Mensaje", alert="Alarma", ev_warning="Alerta", ev_notable="Estación llamativa", ev_clear="Fin de la alerta",
        n_svc="Enviar notificaciones a", n_notable="Notificar también una estación llamativa", n_clear="Notificar el fin de la alerta",
        d_n_svc="Servicios notify, por ejemplo notify.mobile_app_telefono. Vacío: sin notificaciones. Las entidades y el evento funcionan igualmente.",
        d_n_notable="Si no, solo en caso de alerta (estación llamativa a barlovento).", d_n_clear="Cuando el nivel vuelve a tranquilo.",
        title="Radiation Watch",
        desc="Estaciones de tasa de dosis alrededor de su hogar (red alemana BfS y red europea EURDEP), alerta temprana según el viento y una tarjeta de mapa. Los mosaicos de OpenStreetMap se descargan una sola vez y luego se sirven localmente.",
        lat="Latitud", lon="Longitud", near="Radio cercano", far="Radio lejano", wind="Entidad meteorológica para el viento", wfb="Entidad meteorológica de reserva", scan="Intervalo de actualización",
        d_lat="Centro del mapa, por defecto la ubicación de Home Assistant.", d_near="Radio de la vista cercana.",
        d_far="Radio de la vista lejana y de la búsqueda de estaciones. Las estaciones más lejanas se ignoran.",
        d_wind="Proporciona la dirección y la velocidad del viento (atributos wind_bearing y wind_speed).", d_wfb="Se usa cuando la primera no tiene datos de viento.",
        abs="Umbral absoluto", fac="Factor sobre la mediana", off="Distancia mínima sobre la mediana", sec="Sector del viento", minw="Velocidad mínima del viento", age="Antigüedad máxima de los datos",
        d_abs="Una estación a partir de este valor siempre es llamativa.",
        d_fac="Una estación es llamativa si supera mediana x factor y mediana + distancia mínima.",
        d_sec="Una estación llamativa dentro de este ángulo a ambos lados de la dirección del viento genera una alerta.",
        d_minw="Por debajo, la dirección del viento es demasiado inestable.", d_age="Las mediciones más antiguas se descartan.",
        opt_title="Opciones de Radiation Watch", opt_desc="Cambiar la ubicación o los radios vuelve a generar las imágenes del mapa.",
        err_far="El radio lejano debe ser mayor que el radio cercano.", ab="Radiation Watch ya está configurado.",
        st="Estaciones", ew="Alerta temprana", calm="Tranquilo", notable="Llamativo", warning="Alerta", btn="Regenerar mapa",
    ),
}


def build(t: dict) -> dict:
    base_data = {"latitude": t["lat"], "longitude": t["lon"], "radius_near": t["near"], "radius_far": t["far"],
                 "wind_entity": t["wind"], "wind_fallback": t["wfb"], "scan_interval": t["scan"]}
    base_desc = {"latitude": t["d_lat"], "radius_near": t["d_near"], "radius_far": t["d_far"],
                 "wind_entity": t["d_wind"], "wind_fallback": t["d_wfb"]}
    rules_data = {"abs_threshold": t["abs"], "median_factor": t["fac"], "median_offset": t["off"],
                  "sector": t["sec"], "min_wind": t["minw"], "max_age": t["age"]}
    notify_data = {"notify_services": t["n_svc"], "notify_notable": t["n_notable"], "notify_all_clear": t["n_clear"]}
    notify_desc = {"notify_services": t["d_n_svc"], "notify_notable": t["d_n_notable"], "notify_all_clear": t["d_n_clear"]}
    rules_desc = {"abs_threshold": t["d_abs"], "median_factor": t["d_fac"], "median_offset": t["d_fac"],
                  "sector": t["d_sec"], "min_wind": t["d_minw"], "max_age": t["d_age"]}
    return {
        "config": {
            "step": {"user": {"title": t["title"], "description": t["desc"], "data": base_data, "data_description": base_desc}},
            "error": {"far_not_larger": t["err_far"]},
            "abort": {"already_configured": t["ab"], "single_instance_allowed": t["ab"]},
        },
        "options": {
            "step": {"init": {"title": t["opt_title"], "description": t["opt_desc"],
                              "data": {**base_data, **rules_data, **notify_data},
                              "data_description": {**base_desc, **rules_desc, **notify_desc}}},
            "error": {"far_not_larger": t["err_far"]},
        },
        "entity": {
            "sensor": {
                "stations": {"name": t["st"]},
                "early_warning": {"name": t["ew"], "state": {"calm": t["calm"], "notable": t["notable"], "warning": t["warning"]}},
                "message": {"name": t["msg"]},
            },
            "binary_sensor": {"warning": {"name": t["bs"]}},
            "event": {"alert": {"name": t["alert"], "state_attributes": {"event_type": {"state": {
                "warning": t["ev_warning"], "notable": t["ev_notable"], "all_clear": t["ev_clear"]}}}}},
            "button": {"regenerate_map": {"name": t["btn"]}},
        },
    }


if __name__ == "__main__":
    out = Path(__file__).resolve().parent.parent / "custom_components" / "radiation_watch" / "translations"
    out.mkdir(parents=True, exist_ok=True)
    for lang, t in TEXT.items():
        (out / f"{lang}.json").write_text(json.dumps(build(t), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("wrote", lang)
