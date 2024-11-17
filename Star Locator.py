from astropy import coordinates as coords
from astropy.time import Time
import astropy.units as u
from astroquery.simbad import Simbad
import datetime
import warnings
import RPi.GPIO as GPIO
import time
from bluedot.btcomm import BluetoothServer
from signal import pause
from astropy.coordinates import get_body
from astropy.coordinates import solar_system_ephemeris



class StepperMotor:

    def __init__(self):
        self.IN1 = self.IN2 = self.IN3 = self.IN4 = -1
        self.steps_per_revolution = 512
        self.currentPos = 0
        self.step_sequence = [
            [1, 0, 0, 0],
            [1, 1, 0, 0],
            [0, 1, 0, 0],
            [0, 1, 1, 0],
            [0, 0, 1, 0],
            [0, 0, 1, 1],
            [0, 0, 0, 1],
            [1, 0, 0, 1]
        ]

    def motorInit(self, pin1, pin2, pin3, pin4):
        self.IN1 = pin1
        self.IN2 = pin2
        self.IN3 = pin3
        self.IN4 = pin4

    def step_motor(self, steps, delay):
        if self.IN1 != -1:
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            GPIO.setup(self.IN1, GPIO.OUT)
            GPIO.setup(self.IN2, GPIO.OUT)
            GPIO.setup(self.IN3, GPIO.OUT)
            GPIO.setup(self.IN4, GPIO.OUT)
        else:
            print('Motor not initialized!')
            exit()

        if steps < 0:
            self.step_sequence.reverse()

        for _ in range(abs(steps)):
            for step in self.step_sequence:
                GPIO.output(self.IN1, step[0])
                GPIO.output(self.IN2, step[1])
                GPIO.output(self.IN3, step[2])
                GPIO.output(self.IN4, step[3])
                time.sleep(delay)

        if steps < 0:
            self.step_sequence.reverse()

    def rotate(self, degrees, delay=0.001):
        steps = int((degrees / 360.0) * self.steps_per_revolution)
        self.step_motor(steps, delay)
        self.currentPos += degrees

    def goto(self, degrees, delay=0.001):
        rotateVal = degrees - self.currentPos
        while not (rotateVal >= -180 and rotateVal <= 180):
            if rotateVal > 180:
                rotateVal -= 360
            elif rotateVal < -180:
                rotateVal += 360
        self.rotate(rotateVal, delay)

    def resetMotorPos(self):
        self.currentPos = 0
        rotateVal = 0



observerLat = 0
observerLon = 0
observerElev = 0
hrDelta = 0
minDelta = 0

motor1 = StepperMotor()
motor2 = StepperMotor()
motor1.motorInit(17, 18, 27, 22)
motor2.motorInit(16, 20, 21, 26)
mtrSpeed = 1

receivedData = None


def mainFunc(name):

    objectName = ''

    while receivedData is None:
        pause()

    objectName = name    

    observerLocation = coords.EarthLocation(lat=observerLat * u.deg, lon=observerLon * u.deg, height=observerElev * u.m)

    currentTimeUTC = datetime.datetime.now(datetime.timezone.utc)
    currentTime = Time(currentTimeUTC)

    def get_coordinates(objectName):

        SSNames = ["mercury", "venus", "mars", "jupiter", "saturn", "uranus", "neptune", "sun", "moon", "pluto"]
        if objectName.lower() in SSNames:
            with solar_system_ephemeris.set('jpl'):
                return get_body(objectName.lower(), currentTime)


        simbad = Simbad()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = simbad.query_object(objectName)

            if len(w) > 0 and isinstance(w[-1].message, UserWarning):
                return None

            if result is not None:
                ra = result['RA'][0]
                dec = result['DEC'][0]
                return coords.SkyCoord(ra=ra, dec=dec, unit=(u.hourangle, u.deg), frame='icrs')

        return None

    objectCoords = get_coordinates(objectName)

    if objectCoords is None:

        if not objectName.lower() == 'earth':
            print(f"Object '{objectName}' not found.\n")
            s.send(f"Object '{objectName}' not found.\n")

        else:
            print("You're Here!!! Try an other option\n")
            s.send("You're Here!!! Try an other option\n")
            print(objectName.lower())
        
    else:
        
        currentTimeLocal = currentTimeUTC + datetime.timedelta(hours=hrDelta, minutes=minDelta)
        objectAltAz = objectCoords.transform_to(coords.AltAz(obstime=currentTime, location=observerLocation))

        objData = f"Object: {objectName}\nCurrent Time (Local): {currentTimeLocal.isoformat().replace('T', '   ')[:21]}\nAltitude: {objectAltAz.alt.deg:.2f} degrees\nAzimuth: {objectAltAz.az.deg:.2f} degrees\n\n"
        print(objData)
        s.send(objData)
        
        motor1.goto(360-int(objectAltAz.az.deg), 0.005)
        motor2.goto(-int(objectAltAz.alt.deg), 0.005)


def dataReceived(data):

    global receivedData, mtrSpeed, observerLat, observerLon, observerElev, hrDelta, minDelta
    receivedData = data

    cleanData = ''

    for i in receivedData:
        if i.isalnum() or ord(i) in [32, 43, 45, 46, 47, 58]:
            cleanData += i

    try:
        
        if cleanData in ['AZP', 'AZM', 'ALP', 'ALM']:
            
            if cleanData == 'AZP':
                motor1.rotate(-(mtrSpeed))
            elif cleanData == 'AZM':
                motor1.rotate((mtrSpeed))
            elif cleanData == 'ALP':
                motor2.rotate(-(mtrSpeed))
            elif cleanData == 'ALM':
                motor2.rotate((mtrSpeed))
            time.sleep(0.1)
            print(mtrSpeed)
            cleanData = ''
            motor1.resetMotorPos()
            motor2.resetMotorPos()

        elif "Speed: " in cleanData:
            mtrSpeed = int(cleanData[7:])
            cleanData = ''

        elif 'LAT' in cleanData and 'LON' in cleanData and 'ELE' in cleanData and 'TMZ' in cleanData:
            observerLat = float(cleanData[3:cleanData.find('LON')])
            observerLon = float(cleanData[cleanData.find('LON')+3:cleanData.find('ELE')])
            observerElev = float(cleanData[cleanData.find('ELE')+3:cleanData.find('TMZ')])
            hrDelta = int(cleanData[cleanData.find('TMZ')+4:cleanData.find(':')])
            minDelta = int(cleanData[cleanData.find(':')+1:])

            if cleanData[cleanData.find('TMZ')+3:cleanData.find('TMZ')+4] == '+':
                pass
            elif cleanData[cleanData.find('TMZ')+3:cleanData.find('TMZ')+4] == '-':
                hrDelta = -hrDelta
                minDelta = -minDelta

            print(observerLat, observerLon, observerElev, hrDelta, minDelta)


        else:
            mainFunc(cleanData)

    except ValueError:
        time.sleep(0.1)


s = BluetoothServer(dataReceived)
pause()
