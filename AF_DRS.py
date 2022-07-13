# Name:       	AF DRS
# Version:    	v1.0.1
# Author:     	Adder
# AF Author: 	Daniel Ricciardo, Josh Brookes	
# Date:       	27.02.2018, 07.03.2022
# Desc.:      	This app provides a ruleset for ASSETTO FRIENDS AF1 races that use DRS and other rulings
#
# Thanks:     - Rombik: sim_info module
#             - RPMBeeper app: beep code and beep sound

import ac
import acsys
import sys
import os
import time
import configparser
import platform
import traceback
import threading
import hashlib

appName = 'AF_DRS'
imgPath = ('apps/python/%s/img/' % appName)
penaltyFlag = 'content/gui/flags/penalty.png'

# import libraries
try:
    if platform.architecture()[0] == "64bit":
        sysdir = 'apps/python/%s/dll/stdlib64' % appName
    else:
        sysdir = 'apps/python/%s/dll/stdlib' % appName
    sys.path.insert(0, sysdir)
    os.environ['PATH'] = os.environ['PATH'] + ";."
    
    from lib.sim_info import info
    
    import ctypes
    from sound_player import SoundPlayer
    
except Exception as e:
    ac.log(appName + ": Error importing libraries: %s" % e)
    msg = 'Exception: {}'.format(traceback.format_exc())
    ac.log(msg)
    # raise

#globals
updateTime = 1000 / 30 #30 Hz because I felt like it!
audio = ('apps/python/%s/beep.wav' % appName)
sound_player = SoundPlayer(audio)
session = -1

lastUpdateTime = 0
drsData = None      # Definitions of DRS zones.
driverData = None   # Data of last drs detection line each driver crossed and tracking of player info
settings = None     # App settings
rules = None        # Rules
validCar = False    # Flag that aborts the app if not driver car not in list in rules

#acMain set up UI and initilase structures.
def acMain(ac_version):
    try:
        global appName, drsData, driverData, settings, rules
        
        settings = appSettings()
        rules = ruleSet() 
        
        car = ac.getCarName(0)
        if car not in settings.allowedCars:
            ac.log(appName + ": not an allowed car closing app")
            settings.appRunning = False
            return
            
        serverName = ac.getServerName() 
        ac.log(appName + ": Server: %s" % serverName)
        for x in settings.serverNames:
           ac.log(appName + ": Check for: |%s|" % x) 
            
        if any(name in serverName for name in settings.serverNames):
            ac.log(appName + ": match found") 
            settings.postChat = True
            # delay on displaying app running message to make sure things are running
            timer = threading.Timer(10, announceAppRunning)
            timer.start()    
        
        drsData = drs()
        driverData = driverInfo()
        
        ac.log(appName + ": acMain complete")
    except Exception as e:
        ac.log(appName + ": Error in acMain: %s" % e)
        msg = 'Exception: {}'.format(traceback.format_exc())
        ac.log(msg)    

def acUpdate(deltaT):
    try:
        global lastUpdateTime, driverData, session, settings
        
        if settings.appRunning is False:
            return
        
        lastUpdateTime += deltaT
        if lastUpdateTime < float(updateTime)/1000:
            return
        lastUpdateTime = 0        
        
        lastSession = session
        session = info.graphics.session
        
        if session == 1:
            if lastSession != session:
                #gone to Q set visibilities
                ac.setVisible(driverData.penIcon, 0)
                ac.setVisible(driverData.penCounter, 0)
                ac.setVisible(driverData.drsIcon, 0)
                ac.setVisible(driverData.qTyreLabel, 1)
            # Quali need to find tyres used on best lap
            driverData.qualiUpdate()
        elif session == 2:
            # Race
            if lastSession != session:
                #gone to Race set visibilities
                ac.setVisible(driverData.penIcon, 0)
                ac.setVisible(driverData.penCounter, 0)
                ac.setVisible(driverData.drsIcon, 1)
                ac.setVisible(driverData.qTyreLabel, 0)
            # Start tyre = quali tyre
            # Start fuel > minimum
            # DRS used within 1s of car ahead and from lap 3 onwards
            # At least 2 compounds used
            driverData.raceUpdate()
        else:
            #any other session turn everything off
            ac.setVisible(driverData.penIcon, 0)
            ac.setVisible(driverData.penCounter, 0)
            ac.setVisible(driverData.drsIcon, 0)
            ac.setVisible(driverData.qTyreLabel, 0)
            
    except Exception as e:
        ac.log(appName + ": Error in acUpdate: %s" % e)
        msg = 'Exception: {}\n{}'.format(time.asctime(), traceback.format_exc())
        ac.log(msg)    

def announceAppRunning():
    try:
        hasher = hashlib.md5()
        with open(('apps/python/%s/%s.py' % (appName,appName)), 'rb') as afile:
            buf = afile.read()
            hasher.update(buf)
        
        hasher2 = hashlib.md5()
        with open(('apps/python/%s/rules.ini' % appName), 'rb') as afile:
            buf = afile.read()
            hasher2.update(buf)
            
        ac.sendChatMessage(appName + " is running. DRSGap=" + str(rules.drsGap) + "; DRSLap=" + str(rules.drsEnabledLap) + "; Fuel=" + str(rules.refuelling))
        ac.sendChatMessage(appName + (" App  checksum: %s" % hasher.hexdigest()))
        ac.sendChatMessage(appName + (" Rule checksum: %s" % hasher2.hexdigest()))
        
        ac.log(appName + ": Report app running. App checksum: %s" % hasher.hexdigest())
        ac.log(appName + ": Rule checksum: %s" % hasher2.hexdigest())
    except Exception as e:
        ac.log(appName + ": Error in announceApp: %s" % e)
        
def announcePenalty(pen):
    try:
        global settings
        
        if settings.postChat is False:
            return
            
        ac.sendChatMessage(appName + ": Penalty, Lap: %d Detail: %s" % (pen["lap"], pen["detail"]))
        
    except Exception as e:
        ac.log(appName + ": Error in announce penalty: %s" % e)

def renderCallback(deltaT):
    try:
        global driverData
        ac.setBackgroundOpacity(driverData.app, driverData.opacity)
    except Exception as e:
        ac.log(appName + ": Error in renderCallback: %s" % e)
        
def onChatMessage(msg, sender):
    global driverData
    try:
        if(sender == "SERVER"):
            if("You have finished the race" in msg):
                driverData.finishedRace = True
    except Exception as e:
        ac.log(appName + ": Error in onChatMessage: %s" % e)

# was a JSON call updated to python API - JSON modules removed       
def getTrackLength():
    try:
        trackLengthFloat = ac.getTrackLength(0)

        return trackLengthFloat
    except Exception as e:
        ac.log(appName + ": Error in getTrackLength: %s" % e)
        return 0
 
class appSettings:
    def __init__(self):
        try:
            self.opacity = 0.5
            self.scale = 1.0
            self.minimal = True
            self.beepOn = True
            self.beepLength = 0.5
            self.border = True
            
            self.appRunning = True
            self.postChat = False
            self.allowedCars = []
            self.serverNames = []
            
            config = configparser.ConfigParser()
            config.read('apps/python/%s/preferences.ini' % appName)
            
            self.opacity = config.getfloat('Main','BackgroundOpacity')
            if self.opacity < 0:
                self.opacity = 0
            elif self.opacity > 1.0:
                self.opacity = 1.0
            
            border = config.getint('Main','Border')
            if border == 0:
                self.border = False
            
            self.scale = config.getfloat('Main','AppScale')
            
            min = config.getint('Main','Minimal')
            if min == 0:
                self.minimal = False
                
            beep = config.getint('Beep','BeepEnabled')
            if beep == 0:
                self.beepOn = False
            self.beepLength = config.getfloat('Beep','BeepLength')
            
            cars = config.items( "Cars" )
            for key, car in cars:
                self.allowedCars.append(car)
                
            servers = config.items( "Servers" )
            for key, server in servers:
                self.serverNames.append(server)
            
        except Exception as e:
            ac.log(appName + ": Error in loading appSettings: %s" % e)
            return

class ruleSet:
    def __init__(self):
        try:
            config = configparser.ConfigParser()
            config.read('apps/python/%s/rules.ini' % appName)
            
            self.minCompounds = config.getint('Rules','MinTyreCompounds')
            self.startQTyre = config.getint('Rules','startOnBestQualiTyre')
            self.topXtyreInQ = config.getint('Rules','topXqualiTyre')
            self.refuelling = config.getint('Rules','RefuellingAllowed')
            self.drsGap = config.getfloat('Rules','DRSActivationTime')
            self.drsEnabledLap = config.getint('Rules','DRSEnabledLap')
        except Exception as e:
            ac.log(appName + ": Error in loading rules: %s" % e)
            return
            
class driverInfo:
    def __init__(self):
        global penaltyFlag 
        
        self.qualiTyre = "" # short name of compound that player did best Q lap with
        self.bestQLap = 0   # best Q time
        self.start = False  # race start flag
        self.startFuel = 0  # fuel at race start
        self.lastFuel = 0   # fuel level on previous update
        self.pitFuel = 0    # fuel at pit entry
        self.penalties = [] # list of penalties to be served
        self.timePenalties = [] # list of penalties to be handed out at race end
        self.totalDrivers = ac.getCarsCount()  
        self.lastList = []  # list of driver data from previous update
        self.raceCompounds = [] #list of tyre compounds used in race
        self.lastTime = 0   # time that function was called last time (for interpolation)
        self.trackLength = getTrackLength()
        self.drsValid = False   # Flag for DRS valid (race only) true if lap >=3 and within 1s of a car ahead at detection line
        self.inDrsZone = False  # Flag true if between DRS detection and DRS end
        self.drsPenAwarded = False # Flag true if DRS used illegally and penalty has been given for current zone
        self.raceEnd = False # Flag true if all laps completed
        self.servingPenalty = False # Flag true if in pit lane
        self.penaltyVoid = False # Flag true if stop in pitlane
        self.finishedRace = False # Flag to determine if finished a lap down
        self.lastDRSLevel = 0 #level of DRS in use form physics at lat update
        
        #region app controls
        self.fontSize = 18
        self.opacity = settings.opacity
        
        if settings.minimal is True:
            self.width = 200*settings.scale
            self.height = 30*settings.scale
            penaltyFlag = imgPath + "penalty_small.png"
        else:
            self.width = 150*settings.scale
            self.height = 150*settings.scale
            
        #app
        self.app = ac.newApp(appName)
        ac.addRenderCallback(self.app, renderCallback)
        ac.setSize(self.app, self.width, self.height)
        ac.setBackgroundOpacity(self.app, self.opacity)
        if settings.border is False:
            ac.drawBorder(self.app, 0)
        if settings.minimal is True:
            ac.setTitle(self.app, '')
        # chat listener for race end message
        ac.addOnChatMessageListener(self.app, onChatMessage)
        
        #remove ac logo
        ac.setIconPosition(self.app, -10000, -10000)
        
        self.drsIcon = ac.addButton(self.app, "")
        
        ac.setBackgroundTexture(self.drsIcon, imgPath + "off_box.png")
        ac.drawBorder(self.drsIcon, 0)
        ac.setBackgroundOpacity(self.drsIcon, 0)
        ac.drawBackground(self.drsIcon, 0)
        
        self.penIcon = ac.addButton(self.app, "")
        ac.setBackgroundTexture(self.penIcon, penaltyFlag)
        ac.drawBorder(self.penIcon, 0)
        ac.setBackgroundOpacity(self.penIcon, 0)
        ac.drawBackground(self.penIcon, 0)
        ac.setVisible(self.penIcon, 0)
        
        self.penCounter = ac.addLabel(self.app, "")
        ac.setFontAlignment(self.penCounter, 'right')
        ac.setVisible(self.penCounter, 0)
        
        self.qTyreLabel = ac.addLabel(self.app, "Race Start Tyre: ")
        ac.setFontAlignment(self.qTyreLabel, 'left')
        ac.setVisible(self.qTyreLabel, 0)
        
        if settings.minimal is True:
            ac.setSize(self.drsIcon, 90*settings.scale, 30*settings.scale)
            ac.setPosition(self.drsIcon, 0, 0)
            
            ac.setSize(self.penIcon, 65*settings.scale, 30*settings.scale)
            ac.setPosition(self.penIcon, 95*settings.scale, 0)
            ac.setFontSize(self.penIcon, 30*settings.scale)
            
            ac.setSize(self.penCounter, 65*settings.scale, 30*settings.scale)
            ac.setFontAlignment(self.penCounter, 'right')
            ac.setCustomFont(self.penCounter, 'Segoe UI', 0, 1)
            ac.setPosition(self.penCounter, 95*settings.scale, -6.5*settings.scale)
            ac.setFontSize(self.penCounter, 30*settings.scale)
            
            ac.setSize(self.qTyreLabel, 150*settings.scale, 30*settings.scale)
            ac.setPosition(self.qTyreLabel, 5*settings.scale, 0)
            ac.setFontSize(self.qTyreLabel, 20*settings.scale)
        else:
            ac.setSize(self.drsIcon, 90*settings.scale, 30*settings.scale)
            ac.setPosition(self.drsIcon, 10*settings.scale, 115*settings.scale)
            
            ac.setSize(self.penIcon, 150*settings.scale, 80*settings.scale)
            ac.setPosition(self.penIcon, 10*settings.scale, 35*settings.scale)
            ac.setFontSize(self.penIcon, 36*settings.scale)
            
            ac.setSize(self.penCounter, 150*settings.scale, 80*settings.scale)
            ac.setFontAlignment(self.penCounter, 'left')
            ac.setCustomFont(self.penCounter, 'Segoe UI', 0, 1)
            ac.setPosition(self.penCounter, 10*settings.scale, 35*settings.scale)
            ac.setFontSize(self.penCounter, 36*settings.scale)
            
            ac.setSize(self.qTyreLabel, 150*settings.scale, 80*settings.scale)
            ac.setPosition(self.qTyreLabel, 10*settings.scale, 35*settings.scale)
            ac.setFontSize(self.qTyreLabel, 16*settings.scale)
        #endregion app controls
        
    def raceUpdate(self):
    # Update details for a race session.
        global updateTime, drsData, settings, rules
        
        #region Start stuff
        if self.start is False:
        # Check for first lap starting conditions for resets etc
            if info.graphics.completedLaps == 0 and info.graphics.iCurrentTime <= 0:
            #set fuel as start
                self.start = True
                self.startFuel = self.lastFuel = info.physics.fuel
                self.raceEnd = False
                self.finishedRace = False
        else:
        #try to detect a reduction in fuel so driver has applied throttle so know they have there race fuel and tyres selected
            if info.graphics.iCurrentTime > 5000:    
                # turn off start flag 5s after lights out
                self.start = False
            elif self.lastFuel != 0:
                # start not yet detected so check for fuel drop
                self.lastFuel = info.physics.fuel
                fuelDelta = self.startFuel - self.lastFuel
                if fuelDelta > 0 and fuelDelta < 0.2:
                    # Race started as small reduction in fuel level
                    # Set last fuel to 0 so know I have handled the start
                    self.lastFuel = 0
                    # reset data in case race restart
                    self.penalties = []
                    self.raceCompounds = []
                    self.raceCompounds.append(ac.getCarTyreCompound(0))
                    # Check fuel level and tyre compound
                    self.raceStartCheck()
                else:
                    # Big change in fuel still settting things in UI so update start levels
                    self.startFuel = self.lastFuel
        #endregion Start Stuff
        
        
        #region Tyre stuff (plus race end)
        if self.raceEnd is False:
            if info.graphics.completedLaps == info.graphics.numberOfLaps or self.finishedRace is True:
                # race complete.
                self.raceEnd = True
                # check at least two compounds used
                if rules.minCompounds != 0:
                    if len(self.raceCompounds) < rules.minCompounds:
                        # issue compound penalty
                        penInfo = {
                            "lap": info.graphics.numberOfLaps,
                            "driver": ac.getDriverName(0),
                            "detail": "Driver did not use 2 compounds. (POST RACE)"
                            }
                        self.timePenalties.append(penInfo)
                        announcePenalty(penInfo)
                        ac.log(appName + ": Driver did not use %d compounds." % rules.minCompounds)
                # announce any unserved penalties
                for pen in self.penalties:
                    ac.log(appName + ": Unserved Penalty, Lap: %d Detail: %s" % (pen["lap"], pen["detail"]))
                    pen["detail"] = "UNSERVED %s (POST RACE)" % pen["detail"]
                    announcePenalty(pen)
            else:
                # get current tyre and see if in list if not add
                tyre = ac.getCarTyreCompound(0)
                if not tyre in self.raceCompounds:
                    self.raceCompounds.append(tyre)
        #endregion Tyre stuff
        
        
        #region DRS stuff
        curTime = time.time()
        clientCrossedDRS = -1 # index of DRS zone crossed during this update

        driverList = []
        for index in range(self.totalDrivers):
            driver = {
                "spline":       ac.getCarState(index, acsys.CS.NormalizedSplinePosition),       
                "lastDRS":      0,
                "DRStime":      0
                }
            
            if len(self.lastList) > index:
                # if lastList contains items copy items and check for DRS zone crossings
                lastTick = self.lastList[index] # details about driver form last update
                # copy relevant data
                if lastTick is not None:
                    driver["lastDRS"] = lastTick["lastDRS"]
                    driver["DRStime"] = lastTick["DRStime"]
                
                #spline distance travelled
                splineDist = driver["spline"] - lastTick["spline"]
                
                for id, zone in enumerate(drsData.zones):
                    # loop over DRS data
                    # check for crossing of any drs detection line
                    if splineDist > -0.8:
                        #not a new lap
                        if driver["spline"] >= zone["detection"] and lastTick["spline"] < zone["detection"]:
                            #driver crossed DRS detect line
                            driver["lastDRS"] = id
                            if index == 0:
                                clientCrossedDRS = id
                            elapsedTime = curTime - self.lastTime
                            distTravelled = splineDist * self.trackLength
                            avgSpd = elapsedTime/distTravelled
                            distToLine = (zone["detection"] - lastTick["spline"]) * self.trackLength
                            
                            #set crossed time via interpolation
                            driver["DRStime"] = self.lastTime + distToLine * avgSpd
                            break
                            
                    elif zone["detection"] < 0.1:
                        #new lap and zone just after S/F
                        if driver["spline"] >= zone["detection"] and lastTick["spline"]-1 < zone["detection"]:
                            #driver crossed DRS detect line
                            driver["lastDRS"] = id
                            if index == 0:
                                clientCrossedDRS = id
                            elapsedTime = curTime - self.lastTime
                            distTravelled = (driver["spline"] + (1-lastTick["spline"])) * self.trackLength
                            avgSpd = elapsedTime/distTravelled
                            distToLine = (driver["spline"] - zone["detection"]) * self.trackLength
                            
                            #set crossed time via interpolation
                            driver["DRStime"] = curTime - distToLine * avgSpd
                            break
                            
                    elif zone["detection"] > 0.9:
                        #new lap and zone just before S/F
                        if driver["spline"] + 1 >= zone["detection"] and lastTick["spline"] < zone["detection"]:
                            #driver crossed DRS detect line
                            driver["lastDRS"] = id
                            if index == 0:
                                clientCrossedDRS = id
                            elapsedTime = curTime - self.lastTime
                            distTravelled = (driver["spline"] + (1-lastTick["spline"])) * self.trackLength
                            avgSpd = elapsedTime/distTravelled
                            distToLine = (zone["detection"] - lastTick["spline"]) * self.trackLength
                            
                            #set crossed time via interpolation
                            driver["DRStime"] = self.lastTime + distToLine * avgSpd
                            break
                        
            driverList.append(driver)
        
        if rules.drsGap > 0.0:         
            # Check if client crossed detection and within drsGap of another car
            if clientCrossedDRS != -1:
                # ac.log("I crossed DRS")
                myCar = driverList[0]
                self.drsValid = False
                self.inDrsZone = True
                self.drsPenAwarded = False
                 
                ac.setBackgroundTexture(self.drsIcon, imgPath + "red_box.png")

                #DRS from lap x
                if info.graphics.completedLaps+1 >= rules.drsEnabledLap:
                    #check for 1s rule
                    for index, car in enumerate(driverList):
                        if index == 0:
                            continue
                        if car["lastDRS"] == myCar["lastDRS"] and myCar["DRStime"] - car["DRStime"] <= rules.drsGap:
                            self.drsValid = True
                            # ac.log("And I can use it :) car %d, gap %f. Me: %f other %f" % (index, (myCar["DRStime"] - car["DRStime"]), myCar["DRStime"], car["DRStime"]))
                            ac.setBackgroundTexture(self.drsIcon, imgPath + "green_box.png")
                            break
                
            elif self.inDrsZone is True:
                # Didnt cross a line and in a zone so check to see if I leave it and DRS used only if valid
                zone  = drsData.zones[driverList[0]["lastDRS"]] # data of DRS zone in at last step
                
                # Check DRS used correctly and penalty not already awarded for this zone
                if info.physics.drs > 0 and self.drsValid is False and self.drsPenAwarded is False:
                    # Give a penalty
                    self.drsPenAwarded = True
                    penInfo = {
                        "lap": info.graphics.completedLaps + 1,
                        "driver": ac.getDriverName(0),
                        "detail": ("Illegal DRS use, Zone %d" % (driverList[0]["lastDRS"] + 1))
                        }
                    self.penalties.append(penInfo)
                    ac.log(appName + ": Illegal DRS use.")
                    announcePenalty(penInfo)
                
                # Saftey check for end line near S/F. (not sure necessary)
                if zone["end"] > 0.95 and driverList[0]["spline"] < 0.1:
                    self.inDrsZone = False
                    self.drsValid = False
                    self.drsPenAwarded = False
                    ac.setBackgroundTexture(self.drsIcon, imgPath + "off_box.png")
                # Turn off zone when leave
                if driverList[0]["spline"] >= zone["end"] and self.lastList[0]["spline"] < zone["end"]:
                    self.inDrsZone = False
                    self.drsValid = False
                    self.drsPenAwarded = False
                    ac.setBackgroundTexture(self.drsIcon, imgPath + "off_box.png")
                
                # Play a beep when crossing start line and DRS valid
                if settings.beepOn and self.drsValid and driverList[0]["spline"] >= zone["start"] and self.lastList[0]["spline"] < zone["start"]:
                    sound_player.play(audio)
                    #stop in 0.5s (double beep)
                    timer = threading.Timer(settings.beepLength, sound_player.stop)
                    timer.start()
                #else:
                #    sound_player.stop()
            elif info.physics.drs > 0:
                #enabled DRS at start of race or through back to pit
                if self.lastDRSLevel == 0: 
                    #award penalty on opening only
                    penInfo = {
                        "lap": info.graphics.completedLaps + 1,
                        "driver": ac.getDriverName(0),
                        "detail": ("Illegal DRS use, DRS opened without crossing detection line (Start or backToPit)")
                        }
                    self.penalties.append(penInfo)
                    ac.log(appName + ": Illegal DRS use.")
                    announcePenalty(penInfo)
            
        # end of update save current values into lasts
        self.lastTime = curTime
        self.lastList = driverList
        self.lastDRSLevel = info.physics.drs
        #endregion DRS stuff
        
        
        #region Check penalty being served and for refuel
        if info.graphics.isInPitLane:
            # Check pit fuel set if not set it
            if self.pitFuel <= 0.1:
                self.pitFuel = info.physics.fuel
            # Check that if a driver has a penalty and not already voided.
            if len(self.penalties) > 0 and not self.penaltyVoid:
                # Driver is taking a pit lane penalty.
                if info.physics.speedKmh > 5:
                    # Car has not stopped
                    self.servingPenalty = True
                else:
                    # Car has stopped in pit lane, void penalty.
                    self.penaltyVoid = True
        elif self.servingPenalty is True and self.penaltyVoid is False:
            # Not in pit lane any more, and penalty done correctly
            # No need to check for refuel as car did not stop, back to pits handled by speeding app
            self.pitFuel = 0
                
            # remove zeroth penalty
            penServed = self.penalties.pop(0)
            ac.log(appName + ": Penalty served. Pen lap: %d Detail: %s" % (penServed["lap"],penServed["detail"]))
            self.servingPenalty = False
            self.penaltyVoid = False
        else:
            if self.pitFuel > 0:
                #car left pits
                if self.pitFuel < info.physics.fuel and rules.refuelling == 0:
                    #car refuelled and its illegal to do so
                    penInfo = {
                        "lap": info.graphics.completedLaps + 1,
                        "driver": ac.getDriverName(0),
                        "detail": "Driver refuelled (POST RACE)"
                        }
                    self.timePenalties.append(penInfo)
                    announcePenalty(penInfo)
                    ac.log(appName + ": Driver refuelled")
                self.pitFuel = 0
                
            self.servingPenalty = False
            self.penaltyVoid = False
        #endregion Check penalty being served
        
        #region display penalties
        if len(self.penalties) > 0:
            ac.setVisible(self.penIcon, 1)
            ac.setVisible(self.penCounter, 1)
            if len(self.penalties) > 1:
                ac.setText(self.penCounter, "%3d" % len(self.penalties))
            else:
                ac.setText(self.penCounter, "")
        else:
            ac.setVisible(self.penIcon, 0)
            ac.setVisible(self.penCounter, 0)
        #endregion display penalties
        
    def raceStartCheck(self):
        
        self.timePenalties = []
        
        if rules.startQTyre==1 and rules.topXtyreInQ >= ac.getCarLeaderboardPosition(0):
            #check tyre as rule is on and quli postion in top X
            if ac.getCarTyreCompound(0) != self.qualiTyre and self.qualiTyre != "":
                penInfo = {
                    "lap": 0,
                    "driver": ac.getDriverName(0),
                    "detail": "Incorrect starting tyre. (POST RACE)"
                    }
                self.timePenalties.append(penInfo)
                ac.log(appName + ": Incorrect starting tyre.")
                announcePenalty(penInfo)
            
    def qualiUpdate(self):
    #update details for quali
        #get best lap
        best = ac.getCarState(0, acsys.CS.BestLap)
        
        if best == 0:
            #new quali session so reset
            self.bestQLap = 0
            self.qualiTyre = ""
        elif best < self.bestQLap or self.bestQLap == 0:
            #improved best time so update tyre info
            self.bestQLap = best
            self.qualiTyre = ac.getCarTyreCompound(0)
            ac.setText(self.qTyreLabel, "Race Start Tyre: %s" % self.qualiTyre)
    
class drs:
    def __init__(self):
        self.zones = []
        self.loadZones()
        self.valid = False
        
    def loadZones(self):
        try:
            track_name = ac.getTrackName(0)
            track_config = ac.getTrackConfiguration(0)
            if track_config is not None:
                drsIni = "content\\tracks\\%s\\%s\\%s" % (
                    track_name, track_config, "data\\drs_zones.ini")
            else:
                drsIni = "content\\tracks\\%s\\%s" % (
                    track_name, "data\\drs_zones.ini")
            drsExists = os.path.isfile(drsIni)

            if drsExists:
                config = configparser.ConfigParser()
                config.read(drsIni)
                # ac.log('zone sections: %s' % str(config.sections()))
                for zone in config.sections():
                    zone_info = {
                        "detection": float(config[zone]['DETECTION']),
                        "start": float(config[zone]['START']),
                        "end": float(config[zone]['END'])
                    }
                    ac.log(appName + ': zone %s' % str(zone_info))
                    self.zones.append(zone_info)
            else:
                ac.log(appName + ": could not find drs_zones.ini file")
                return False
        except Exception as e:
            ac.log(appName + ": Error in loadDrsZones: %s" % e)

