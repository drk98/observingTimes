#  Copyright (c) Daniel R. Kramer 2020.

from astroquery.jplhorizons import Horizons
from astropy.time import Time
import configparser
import sys

config = configparser.ConfigParser(allow_no_value=True)
config.read('config.ini')


def getObjects():
    """
    Gets a list of objects to
    :return: List of objects to check observing times
    """
    fileObjects = []
    sqlObjects = []

    if config["OBJECTS"].get("FILE", fallback=False):
        import csv
        with open(config["OBJECTS"]["FILE"], 'r') as csvFile:
            reader = csv.reader(csvFile)
            fileObjects = [r[0] for r in reader]

    if config["OBJECTS"].get("SQLDB", fallback=False):
        import sqlalchemy
        engine = sqlalchemy.create_engine(config["OBJECTS"]["SQLDB"])
        conn = engine.connect()

        table = config["OBJECTS"]["SQLTABLE"]
        idcol = config["OBJECTS"]["SQLID"]

        datacols = config["OBJECTS"].get("SQLCOLUMNS", fallback=None)
        if datacols:
            datacols = datacols.split(',')
            topN = config["OBJECTS"].getint("SQLTOPN", fallback=10)
            desc = config["OBJECTS"].getboolean("SQLDESC", fallback=True)

            for col in datacols:
                res = conn.execute(f"SELECT {idcol} FROM {table} ORDER BY {col} {'DESC' if desc else 'ASC'} LIMIT {topN};")
                for r in res.fetchall():
                    sqlObjects.append(r[0])
        else:
            res = conn.execute(f"SELECT {idcol} FROM {table};")

            for r in res.fetchall():
                sqlObjects.append(r[0])

        # Disconnect from database
        engine.dispose()

    return list(set(fileObjects + sqlObjects))


def getEphemerides(objectID):
    location = config["LOCATION"].get("MPCCODE", fallback=None)
    if not location:
        location = {'lon': config["LOCATION"].getfloat("LONGITUDE"),
                    'lat': config["LOCATION"].getfloat("LATITUDE"),
                    'elevation': config["LOCATION"].getfloat("ELEVATION")}

    epochs = config["EPOCHS"].get("EPOCHS", fallback=None)
    if epochs:
        epochs = epochs.split(',')
    else:
        epochs = {'start': config["EPOCHS"]["STARTDATE"],
                  'stop': config["EPOCHS"]["ENDDATE"],
                  'step': config["EPOCHS"]["STEP"]}
    obj = Horizons(id=objectID, location=location, epochs=epochs)

    try:
        eph = obj.ephemerides(airmass_lessthan=config["EPHEMERIDES"].getfloat("MAXAIRMASS", fallback=6e9),
                              skip_daylight=config["EPOCHS"].getboolean("SKIPDAYLIGHT", fallback=True))
    except ValueError:
        return None

    maxMag = config["EPHEMERIDES"].getfloat("MAXMAG", fallback=6e9)
    return eph[eph["V"] < maxMag]


def graph(ephArr):
    if not config["OUTPUT"].getboolean("GRAPHENABLED", fallback=False):
        return

    import matplotlib.pyplot as plot
    fig = plot.figure()
    ax = fig.add_subplot(111)

    yaxisCol = config["OUTPUT"].get("YAXIS", fallback="V")
    ax.set_title(f"{yaxisCol} vs time")
    yaxisCol = yaxisCol.split(',')
    splitY = False
    ax.set_ylabel(yaxisCol[0])
    ax.set_xlabel("Julian date")

    if len(yaxisCol) == 2:
        splitY = True
        ax2 = ax.twinx()
        ax2.set_ylabel(yaxisCol[1])

    for eph in ephArr:
        objectID = eph["targetname"][0]
        ax.scatter(eph["datetime_jd"], eph[yaxisCol[0]], label=objectID)

        if splitY:
            ax2.scatter(eph["datetime_jd"], eph[yaxisCol[1]], label=objectID)

    plot.legend()
    plot.show()


def main():
    objects = getObjects()

    ephArr = []
    for objectID in objects:
        eph = getEphemerides(objectID)

        if eph:
            print(f"{objectID}: Observable times found")
            ephArr.append(eph)
            t_jd = Time(eph["datetime_jd"], format='jd')

            ephCols = config["OUTPUT"].get("COLUMNS", fallback=None)
            if ephCols:

                ephCols = ephCols.split(',')

                tz = config["OUTPUT"].get("ADDTIMEZONE", fallback=None)
                if tz:
                    import pytz
                    tz = pytz.timezone(tz)
                    timeFormat = config["OUTPUT"].get("TIMEFORMAT", fallback="%Y-%m-%%d - %H:%M:%S")
                    times = [tz.localize(t).strftime(timeFormat) for t in t_jd.datetime]
                    eph["local_time"] = times

                eph[ephCols].pprint_all()
        else:
            print(f"{objectID}: No observable times in the constraints.")

    graph(ephArr)


if __name__ == "__main__":
    main()
