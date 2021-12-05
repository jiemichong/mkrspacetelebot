#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import settings
import secrets
import telegram
import logging
import haversine
import enum
import pprint
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import datetime
from datetime import timedelta, date
import os.path
import gspread
from oauth2client.service_account import ServiceAccountCredentials

from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    ConversationHandler,
    CallbackContext,
    CallbackQueryHandler,
)

# Enable logging
logging.basicConfig(format="%(asctime)s %(levelname)s %(filename)s:%(funcName)s():%(lineno)i: %(message)s", datefmt="%Y-%m-%d %H:%M:%S",  level=logging.DEBUG)
logger = logging.getLogger(__name__)

####################   Borrowing & Lending feature. Works in private chats.
STATE_RETURN_TO_START = "STATE_RETURN_TO_START"

STATE_CHOOSE_TASK_TYPE = "STATE_CHOOSE_TASK_TYPE"
STATE_CHOOSE_DATE     = "STATE_CHOOSE_DATE"
STATE_CHOOSE_LOANING_DETAILS     = "STATE_CHOOSE_LOANING_DETAILS"

STATE_DELETE_APT = "STATE_DELETE_APT"
STATE_CONFIRM_CHOICE = "STATE_CONFIRM_CHOICE"
YEP = "Yep"
NAH = "Nah"

STATE_VERIFY_USER_NAME = "STATE_VERIFY_USER_NAME"
STATE_VERIFY_USER_EMAIL = "STATE_VERIFY_USER_EMAIL"

STATE_CHOOSE_ITEM = "STATE_CHOOSE_ITEM"
STATE_VERIFY_ITEM = "STATE_VERIFY_ITEM"
STATE_VERIFY_QUANTITY = "STATE_VERIFY_QUANTITY"
STATE_UPDATE_LOAN_SHEET = "STATE_UPDATE_LOAN_SHEET"
STATE_LOAN_LOOP = "STATE_LOAN_LOOP"

USER = "USER"
USER_CHOICE = "USER_CHOICE"
USER_BORROW = "borrow"
USER_RETURN = "return"
USER_CANCEL = "USER_CANCEL"
DAY = "DAY"
DATE = "DATE"
TIMESLOT = "TIMESLOT"
CHOOSE_RETURN = "CHOOSE_RETURN"
CHOOSE_CANCEL = "CHOOSE_CANCEL"

STATE_ADMIN_CHOOSE_APPOINTMENT = "STATE_ADMIN_CHOOSE_APPOINTMENT"
STATE_ADMIN_SELECTED_APPOINTMENT_ONLY = "STATE_ADMIN_SELECTED_APPOINTMENT_ONLY"

STATE_ADMIN_EDIT_APPOINTMENT = "STATE_ADMIN_EDIT_APPOINTMENT"
STATE_ADMIN_EDIT_BORROW = "STATE_ADMIN_EDIT_BORROW"
STATE_ADMIN_EDIT_RETURN = "STATE_ADMIN_EDIT_RETURN"
STATE_WAITING_FOR_RFID_NUMBERS = "STATE_WAITING_FOR_RFID_NUMBERS"

TASK_ADMIN_TYPE_APPOINTMENTS = "Pending Appointments"
TASK_ADMIN_TYPE_BORROW = "Process Borrow"
TASK_ADMIN_TYPE_RETURN = "Process Return"
TASK_ADMIN_CURRENT_JOBS = "Current Jobs"

TASK_ADMIN_TYPE_APPROVE_APPOINTMENT = "Approve Appointment"
TASK_ADMIN_TYPE_REJECT_APPOINTMENT = "Reject Appointment"

TASK_ADMIN_TYPE_COMPLETE_BORROW = "Complete Borrow"
TASK_ADMIN_TYPE_CANCEL_BORROW = "Reject Borrow"

TODAY_APPOINTMENTS = "Today Appointments"

####################   Google Sheets setup
SCOPE = ['https://spreadsheets.google.com/feeds',
         'https://www.googleapis.com/auth/drive']
CREDS = ServiceAccountCredentials.from_json_keyfile_name('client_secret.json', SCOPE)
CLIENT = gspread.authorize(CREDS)

SPREADSHEET = CLIENT.open("MakerSpace Loaning Inventory")
AVAILABLE_ITEMS = SPREADSHEET.worksheet("Items Available for Loaning")
LOAN_LIST = SPREADSHEET.worksheet("Loan List")
HISTORY_LIST = SPREADSHEET.worksheet("History of Loans")

ADMINS = ["Jiemii", "splashypop", "synn0", "posfosman"]
AVAILABLE = AVAILABLE_ITEMS.get_all_records()
LOANS = LOAN_LIST.get_all_records()
HISTORY = HISTORY_LIST.get_all_records()
STATUS_COL = 7
RETURN_DATE_COL = 8
ITEMS_COL = 4
ITEM_NAME = 3

current_job = ""
available_for_loan = 0
position = 0

def start(update: Update, context: CallbackContext) -> None:
    # check if the user is an admin
    user = update.message.from_user
    username = user['username']
    context.user_data['username'] = username
    context.user_data['items'] = ""

    if username in ADMINS:
        admin_options(update, context)
        return STATE_CHOOSE_LOANING_DETAILS
    else:
        update.message.reply_text("Welcome to the MakerSpace Bot! I can help you book appointments with the student leaders of Makerspace for the borrowing/return of items in the Makerspace.\n"
        "First, to verify you are a faculty member, please key in your full name:")
        return STATE_VERIFY_USER_NAME

def admin_options(update: Update, context: CallbackContext) :
    keyboard = [[
            InlineKeyboardButton("Appointments", callback_data=TASK_ADMIN_TYPE_APPOINTMENTS),
            InlineKeyboardButton("Borrow", callback_data=TASK_ADMIN_TYPE_BORROW),
            InlineKeyboardButton("Return", callback_data=TASK_ADMIN_TYPE_RETURN),
            ],
            [InlineKeyboardButton("Today's appointment(s)", callback_data=TODAY_APPOINTMENTS)]]
    update.message.reply_text("Welcome to the MakerSpace Bot (Admin Mode)! You can accept appointments and process loans or returns.", reply_markup=InlineKeyboardMarkup(keyboard))
  
## to take in user's full name
def handle_user_name(update: Update, context: CallbackContext) -> None:
    full_name = update.message.text
    context.user_data['full_name'] = full_name
    context.user_data['timeSelected'] = ""
    update.message.reply_text("Next, please type your SMU email:")
    return STATE_VERIFY_USER_EMAIL

## to take in user's email
def handle_user_email(update: Update, context: CallbackContext) -> int:
    email = update.message.text
    context.user_data['email'] = email
    email_suffix = "@smu.edu.sg"
    if (any(char.isdigit() for char in email)):
        #if there are digits in the email, reject
        update.message.reply_text("Sorry! You are not authorized to borrow items from the Makerspace. Please try another email or approach our Makerspace student leaders at t.me/SMUMakerspace for more information!\n Email: ")
        return STATE_VERIFY_USER_EMAIL
    elif (email == email_suffix or email[-11:] != email_suffix):
        #if it is not an email, reject
        update.message.reply_text("Sorry! You have entered an invalid email. Please try to re-enter your email:")
    else:
        #else proceed to next step
        keyboard = [[
            InlineKeyboardButton("Borrow", callback_data=USER_BORROW),
            InlineKeyboardButton("Return", callback_data=USER_RETURN),
            InlineKeyboardButton("Cancel", callback_data=USER_CANCEL),
            ]]
        update.message.reply_text("You are verified! What do you want to do? Cancel means cancel an existing appointment", reply_markup=InlineKeyboardMarkup(keyboard))
        return USER_CHOICE 

def handle_user_choice(update: Update, context: CallbackContext) -> None:
    update.callback_query.answer()
    if update.callback_query.data == USER_CANCEL:
        context.user_data['userChoice'] = USER_CANCEL
        return handle_user_cancel(update,context)
    elif update.callback_query.data == USER_BORROW:
        context.user_data['userChoice'] = USER_BORROW
        return handle_user_loaning(update,context)
    elif update.callback_query.data == USER_RETURN:
        context.user_data['userChoice'] = USER_RETURN
        context.user_data["sn,row"] = ""
        return handle_user_return(update,context)

def get_available_items(i):
    details = "{0:5}".format("/" + str(AVAILABLE[i]["S/N"]))
    details += "{0:20}".format(AVAILABLE[i]["Name"])
    details += "{0:5}".format(AVAILABLE[i]["Quantity"]) + "\n"
    return details

def get_sheets():
    global LOANS
    global AVAILABLE

    LOANS = LOAN_LIST.get_all_records()
    AVAILABLE = AVAILABLE_ITEMS.get_all_records()

def handle_user_return(update: Update, context: CallbackContext) -> None:
    update.callback_query.answer()
    update.callback_query.message.reply_text("Retrieving appointments...")
    keyboard = [[
        InlineKeyboardButton("Borrow", callback_data=USER_BORROW),
        InlineKeyboardButton("Return", callback_data=USER_RETURN),
        InlineKeyboardButton("Cancel", callback_data=USER_CANCEL),
        ]]
    try:
        allLoanRecords =  LOAN_LIST.findall(context.user_data['username'])

        #find all records with status "Issued" in loan list for all incomplete loans
        incompleteLoans = []
        for cell in allLoanRecords:
            row = cell.row
            if(LOAN_LIST.cell(row,STATUS_COL).value == "Issued"):
                incompleteLoans.append(row)
            elif(LOAN_LIST.cell(row,STATUS_COL).value == "Pending Return" or LOAN_LIST.cell(row,STATUS_COL).value == "Approved Return"):
                incompleteLoans.append(row)

        if(not incompleteLoans):
            update.callback_query.message.reply_text(f"You have nothing to return. What do you want to do?", reply_markup=InlineKeyboardMarkup(keyboard))
            return USER_CHOICE
         
        #Check if there is an existing return_date for each incomplete loan 
        #Only allow the faculty to make an appt if no return date is found
        recordsWithReturnAppt = ""
        recordsWithoutReturnAppt = ""
        snReturn = 0
        for row in incompleteLoans:
            allItems = LOAN_LIST.cell(row,ITEMS_COL).value
            items = allItems.split("| ")
            items = items[:-1]
            
            details = ""
            itemsBorrowed = {}
 
            for item in items:
                sn = int(item[0])
                qty = int(item[2:])

                if (not itemsBorrowed.get(sn)):
                    itemsBorrowed[sn] = qty
                else:
                    itemsBorrowed[sn] += qty

            for key, value in itemsBorrowed.items():
                details += AVAILABLE_ITEMS.cell(key+1,ITEM_NAME).value +" qty: " + str(qty) + "\n"
               
            #no appt made to return item
            if( not LOAN_LIST.cell(row,RETURN_DATE_COL).value):
                #get details of item in that loan record 
                recordsWithoutReturnAppt += "/" + str(snReturn) + " Items borrowed:\n" + details
                #store sn, row in context
                context.user_data["sn,row"] += str(snReturn)+"," + str(row) +"| "
                snReturn += 1

            else:
                #records with return appt
                recordsWithReturnAppt += "Return date: " + LOAN_LIST.cell(row, RETURN_DATE_COL).value +" for the following items:\n" +details

        #dont have appts without return appt date
        if(not recordsWithoutReturnAppt):
            if(recordsWithReturnAppt):
                recordsWithReturnAppt = "You have made appointment(s) on these dates. Cancel the appointment(s) to make new appointment(s)\n\n" + recordsWithReturnAppt
            #dont have incomplete loans (not possible btw)
            else:
                recordsWithReturnAppt = "You have no incomplete loans."
            
            update.callback_query.message.reply_text(recordsWithReturnAppt + "What do you want to do?", reply_markup= InlineKeyboardMarkup(keyboard))
            return USER_CHOICE

        recordsWithoutReturnAppt = "You can make an appointment for the following loans by replying with the command (/number).\n" + recordsWithoutReturnAppt
        if(recordsWithReturnAppt):
            recordsWithoutReturnAppt = "You have made appointment(s) on these dates. Cancel the appointment(s) to make new appointment(s)\n" + recordsWithReturnAppt + "\n" + recordsWithoutReturnAppt
        
        recordsWithoutReturnAppt += "/back to exit\n\n"
        update.callback_query.message.reply_text(recordsWithoutReturnAppt)
        return CHOOSE_RETURN
        
    except:
        update.callback_query.message.reply_text(f"You have no loans. What do you want to do? Cancel means cancel an existing appointment", reply_markup=InlineKeyboardMarkup(keyboard))
        return USER_CHOICE

def handle_choose_return(update: Update, context: CallbackContext) -> None:
    message = update.message.text
    # this is the s/n the user enters
    chosen = message[1:]

    # if the choice is a not a number, user needs to re-enter choice and will return to this method again
    if(chosen == "back"):
        update.message.reply_text("Press /start to begin!")
        return STATE_RETURN_TO_START
    elif (not chosen.isdigit()):
        update.message.reply_text("/" + chosen + " is unavailable, please select the choice using the buttons above!")
        return CHOOSE_RETURN
    chosen = int(chosen)
    
    #get row from choice 
    rowInLoan = -1
    availableChoices = context.user_data["sn,row"]
    choices = availableChoices.split("| ")
    choices = choices[:-1]

    for choice in choices: 
        sn = int(choice[0])
        row = int(choice[2:])

        if(sn == chosen):
            rowInLoan = row
        
    context.user_data['chosenRowToReturn'] = rowInLoan
    update.message.reply_text("You have chosen /" + str(chosen))
    keyboard = [
        [ InlineKeyboardButton("Monday", callback_data='1')],
        [ InlineKeyboardButton("Tuesday", callback_data='2')],
        [ InlineKeyboardButton("Wednesday", callback_data='3')],
        [ InlineKeyboardButton("Thursday", callback_data='4')],
        [ InlineKeyboardButton("Friday", callback_data='5')],
        [ InlineKeyboardButton("Saturday", callback_data='6')],
        [ InlineKeyboardButton("Sunday", callback_data='7')],
        [ InlineKeyboardButton("Exit", callback_data='Exit')]
    ]
    update.message.reply_text(text=f"Please indicate the day that you are free in the upcoming week to {context.user_data['userChoice']} your item(s).", reply_markup=InlineKeyboardMarkup(keyboard, one_time_keyboard=True))
    return DAY
    
def handle_user_cancel(update: Update, context: CallbackContext) -> None:
    update.callback_query.answer()
    update.callback_query.message.reply_text("Retrieving appointments ...")
    context.user_data['cancelSn,row'] = ""
    
    keyboard = [[
        InlineKeyboardButton("Borrow", callback_data=USER_BORROW),
        InlineKeyboardButton("Return", callback_data=USER_RETURN),
        InlineKeyboardButton("Cancel", callback_data=USER_CANCEL),
    ]]

    try:
        allLoanRecords =  LOAN_LIST.findall(context.user_data['username'])
        incompleteLoans = {}
        #most recent incomplete loan record
        for cell in (allLoanRecords):
            row = cell.row
            if(LOAN_LIST.cell(row,STATUS_COL).value == "Approved Return"):
                incompleteLoans[row] = "Approved Return"
            elif(LOAN_LIST.cell(row,STATUS_COL).value == "Approved Borrow"):
                incompleteLoans[row] = "Approved Borrow"
            elif(LOAN_LIST.cell(row, STATUS_COL).value == "Pending Return"):
                incompleteLoans[row] = "Pending Return"
            elif(LOAN_LIST.cell(row, STATUS_COL).value == "Pending Borrow"):
                incompleteLoans[row] = "Pending Borrow"
        
        if(not incompleteLoans):
            update.callback_query.message.reply_text(f"There is no appointments to cancel. What do you want to do?", reply_markup=InlineKeyboardMarkup(keyboard))
            return USER_CHOICE

        snReturned = 0
        returnAppt = ""
        borrowAppt = ""
        for row,status in incompleteLoans.items():
            allItems = LOAN_LIST.cell(row,ITEMS_COL).value
            items = allItems.split("| ")
            items = items[:-1]
            
            details = ""
            itemsBorrowed = {}
 
            for item in items:
                sn = int(item[0])
                qty = int(item[2:])
                if (not itemsBorrowed.get(sn)):
                    itemsBorrowed[sn] = qty
                else:
                    itemsBorrowed[sn] += qty

            for key, value in itemsBorrowed.items():
                details += AVAILABLE_ITEMS.cell(key+1,ITEM_NAME).value +" qty: " + str(qty) + "\n"
            
            if(status == "Approved Return" or status == "Pending Return"):
                returnAppt += "/" + str(snReturned) + " Items to Return:\n" + details
            elif(status == "Approved Borrow" or status == "Pending Borrow"):
                borrowAppt += "/" + str(snReturned) + " Items Borrowed:\n" + details

            context.user_data["cancelSn,row"] += str(snReturned) +"," + str(row) + "| "
            snReturned += 1
    
        update.callback_query.message.reply_text("Choose an appointment to cancel.\n" + returnAppt + borrowAppt +"Press /back to go back\n")
        return CHOOSE_CANCEL
    except Exception as e :
        print("EXCEPTION")
        print(e)
        keyboard = [[
            InlineKeyboardButton("Borrow", callback_data=USER_BORROW),
            InlineKeyboardButton("Return", callback_data=USER_RETURN),
            InlineKeyboardButton("Cancel", callback_data=USER_CANCEL),
            ]]
        update.callback_query.message.reply_text("You have no current bookings! What do you want to do now?", reply_markup=InlineKeyboardMarkup(keyboard))
        return USER_CHOICE

def handle_choose_cancel(update:Update, context: CallbackContext) -> None:
    message = update.message.text
    # this is the s/n the user enters
    chosen = message[1:]

    if(chosen == "back"):
        keyboard = [[
            InlineKeyboardButton("Borrow", callback_data=USER_BORROW),
            InlineKeyboardButton("Return", callback_data=USER_RETURN),
            InlineKeyboardButton("Cancel", callback_data=USER_CANCEL),
            ]]
        update.message.reply_text("What do you want to do now?", reply_markup=InlineKeyboardMarkup(keyboard))
        return USER_CHOICE
    
    # if the choice is a not a number, user needs to re-enter choice and will return to this method again
    elif (not chosen.isdigit()):
        update.message.reply_text("/" + chosen + " is unavailable, please select the choice using the buttons above!")
        return CHOOSE_CANCEL
    
    update.message.reply_text("Canceling appointment ...")

    chosen = int(chosen)

    rowInLoan = -1
    availableChoices = context.user_data["cancelSn,row"]
    choices = availableChoices.split("| ")
    choices = choices[:-1]

    for choice in choices: 
        print(choice)
        sn = int(choice[0])
        row = int(choice[2:])

        if(sn == chosen):
            rowInLoan = row

    #if its borrow --> update available items
    if(LOAN_LIST.cell(rowInLoan,STATUS_COL).value == "Approved Borrow" or LOAN_LIST.cell(rowInLoan,STATUS_COL).value == "Pending Borrow"):
        itemsBorrowed = LOAN_LIST.cell(rowInLoan, ITEMS_COL).value.split('|')
        itemsBorrowed = itemsBorrowed[:-1] #remove last empty value
        for item in itemsBorrowed:
            splitItem = item.split(",")
            sn = int(splitItem[0])
            qty = int(splitItem[1])
            update_row = AVAILABLE_ITEMS.row_values(sn + 1)

            prevQty = int(AVAILABLE_ITEMS.cell(sn+1,4).value)
            prevHold =  int(AVAILABLE_ITEMS.cell(sn+1,5).value)
            print("PREV QTY " + str(prevQty))
            print("PREV HOLD " + str(prevHold))
            newHold = prevHold - qty
            newQty = prevQty + qty
            AVAILABLE_ITEMS.update_cell(sn + 1, 4, newQty)
            AVAILABLE_ITEMS.update_cell(sn + 1, 5, newHold)

            #move to history 
            HISTORY_LIST.append_row(LOAN_LIST.row_values(rowInLoan))
            #remove from LOAN_LIST
            LOAN_LIST.delete_row(rowInLoan)
    elif(LOAN_LIST.cell(rowInLoan,STATUS_COL).value == "Approved Return" or LOAN_LIST.cell(rowInLoan,STATUS_COL).value == "Pending Return"):
        LOAN_LIST.update_cell(rowInLoan,STATUS_COL, "Issued")
        LOAN_LIST.update_cell(rowInLoan,RETURN_DATE_COL, "")

    keyboard = [[
        InlineKeyboardButton("Borrow", callback_data=USER_BORROW),
        InlineKeyboardButton("Return", callback_data=USER_RETURN),
        InlineKeyboardButton("Cancel", callback_data=USER_CANCEL),
    ]]
    update.message.reply_text("Okay your appointment has been cancelled successfully. What do you want to do now?", reply_markup=InlineKeyboardMarkup(keyboard))
    return USER_CHOICE

# prints list of items available for borrowing
def handle_user_loaning(update: Update, context: CallbackContext) -> None:
    update.callback_query.answer()
    get_sheets()

    itemsAvailable = False
    to_print = "List of items available for borrowing & their quantity: \n"
    for i in range (len(AVAILABLE)):
        if (AVAILABLE[i]['Quantity'] != 0):
            itemsAvailable = True
            to_print += get_available_items(i) + "\n"
    to_print += "/exit to quit booking\n/next to move on\n"
    to_print += "Please indicate the item that you wish to loan out:"

    if itemsAvailable:
        update.callback_query.message.reply_text(to_print)
        return STATE_VERIFY_ITEM
    else: 
        update.callback_query.message.reply_text("There is nothing available for loan. Type /start if you want to do something else!")
        if len(context.user_data['items']) != 0:
            return user(update, context)
        else:
            update.callback_query.message.reply_text("Byebye! Type /start if you want to do something else!")
            return STATE_RETURN_TO_START

# handles user's choice of item to loan and prompts user for quantity
def handle_verify_item(update: Update, context: CallbackContext) -> None:
    index = 0
    message = update.message.text
    # this is the s/n the user enters
    choice = message[1:]
    context.user_data['choice'] = choice
        
    # if the choice is a not a number, user needs to re-enter choice and will return to this method again
    if(choice == "exit"):
        if(context.user_data['items']):
            #remove selected items 
            remove_selected_items(context.user_data['items'])
        update.message.reply_text("ByeBye! Type /start if you want to do something else!\n")
        return STATE_RETURN_TO_START
    elif(choice == "next"):
        if(not context.user_data['items']):
            get_sheets()
            itemsAvailable = False
            to_print = "List of items available for borrowing & their quantity: \n"
            for i in range (len(AVAILABLE)):
                if (AVAILABLE[i]['Quantity'] != 0):
                    itemsAvailable = True
                    to_print += get_available_items(i) + "\n"
            to_print += "/exit to quit booking\n/next to move on\n"
            to_print += "Please indicate the item that you wish to loan out:"
            update.message.reply_text("You have not selected anything.\n" + to_print)
            return STATE_VERIFY_ITEM
        else: 
            keyboard = [
                [ InlineKeyboardButton("Monday", callback_data='1')],
                [ InlineKeyboardButton("Tuesday", callback_data='2')],
                [ InlineKeyboardButton("Wednesday", callback_data='3')],
                [ InlineKeyboardButton("Thursday", callback_data='4')],
                [ InlineKeyboardButton("Friday", callback_data='5')],
                [ InlineKeyboardButton("Saturday", callback_data='6')],
                [ InlineKeyboardButton("Sunday", callback_data='7')],
                [ InlineKeyboardButton("Exit", callback_data='Exit')]
            ]
            update.message.reply_text(text=f"Please indicate the day that you are free in the upcoming week to {context.user_data['userChoice']} your item(s).", reply_markup=InlineKeyboardMarkup(keyboard, one_time_keyboard=True))
            return DAY
    elif (not choice.isdigit() or AVAILABLE[int(choice) - 1]['Quantity'] == 0):
        update.message.reply_text("/" + choice + " is unavailable, please select the choice using the buttons above!")
        return STATE_VERIFY_ITEM
    choice = int(choice)

    global position
    for i in range(len(AVAILABLE)):
        if (AVAILABLE[i]["S/N"] == choice):
            position = i
            break

    global available_for_loan
    available_for_loan = AVAILABLE[position]["Quantity"]
    # print out the item name
    to_print = AVAILABLE[position]["Name"] + "\n"
    # print out available quantity
    to_print += "Available Quantity: " + str(available_for_loan) + "\n"
    update.message.reply_text(to_print + "/back to return to selection of items.\nPlease indicate the quantity you wish to loan out: \n")
    return STATE_VERIFY_QUANTITY

# handle's user's input for quantity of item they want to borrow
def handle_quantity(update: Update, context: CallbackContext) -> None:
    global available_for_loan
    global position
    # get user's reply about quantity
    quantity = update.message.text
    context.user_data['quantity'] = quantity

    # check if the quantity is not a digit, will return to this method when user replies again
    if(quantity == "/back"):
        get_sheets()
        itemsAvailable = False
        to_print = "List of items available for borrowing & their quantity: \n"
        for i in range (len(AVAILABLE)):
            if (AVAILABLE[i]['Quantity'] != 0):
                itemsAvailable = True
                to_print += get_available_items(i) + "\n"
        to_print += "/exit to quit booking\n/next to move on\n"
        to_print += "Please indicate the item that you wish to loan out:"
        update.message.reply_text("You have not selected anything. Please press /exit to exit.\n" + to_print)
        return STATE_VERIFY_ITEM
    elif (not quantity.isdigit() or int(quantity) <= 0):
        update.message.reply_text("Invalid choice, please select a numeric quantity greater than 0!")
        return STATE_VERIFY_QUANTITY
    # convert quantity to a number
    quantity = int(quantity)

    # if the user inputs a number more than what's available, print out quantity available again and return to this method
    # when user replies again
    if quantity > available_for_loan:
        to_print = AVAILABLE[position]["Name"] + "\n"
        to_print += "Available Quantity: " + str(available_for_loan) + "\n"
        update.message.reply_text(to_print + "Sorry! There isn't enough quantity to fulfill your loan! Please indicate a lower quantity: ")
        return STATE_VERIFY_QUANTITY
    else:
        # if the quantity is ideal update the balance in the available list
        get_sheets()
        balance = available_for_loan - quantity
        hold = quantity + AVAILABLE[position]["Hold"]
        AVAILABLE_ITEMS.update_cell(position + 2, 4, balance)
        AVAILABLE_ITEMS.update_cell(position + 2, 5, hold)
        # item_and_quantity = LOANS[len()][4]
        context.user_data['items'] += str(context.user_data['choice']) + ", " + str(context.user_data['quantity'] + "| ")

        keyboard = [[
            InlineKeyboardButton("Yes", callback_data=YEP),
            InlineKeyboardButton("No", callback_data=NAH)
            ]]
        update.message.reply_text("Your requested items has been recorded. Do you wish to borrow another item?", reply_markup=InlineKeyboardMarkup(keyboard))
        return STATE_LOAN_LOOP

def handle_loan_loop(update: Update, context: CallbackContext) -> None:
    if update.callback_query.data == YEP:
        return handle_user_loaning(update,context)
    else:
        return user(update,context)

def user(update: Update, context: CallbackContext) -> str:
    update.callback_query.answer()
    
    keyboard = [
        [ InlineKeyboardButton("Monday", callback_data='1')],
        [ InlineKeyboardButton("Tuesday", callback_data='2')],
        [ InlineKeyboardButton("Wednesday", callback_data='3')],
        [ InlineKeyboardButton("Thursday", callback_data='4')],
        [ InlineKeyboardButton("Friday", callback_data='5')],
        [ InlineKeyboardButton("Saturday", callback_data='6')],
        [ InlineKeyboardButton("Sunday", callback_data='7')],
        [ InlineKeyboardButton("Exit", callback_data='Exit')]
    ]
    update.callback_query.message.reply_text(text=f"Please indicate the day that you are free in the upcoming week to {context.user_data['userChoice']} your item(s).", reply_markup=InlineKeyboardMarkup(keyboard, one_time_keyboard=True))
    return DAY

def stringDay(day):
    if(day == 1):
        return "Monday"
    elif (day == 2):
        return "Tuesday"
    elif (day == 3):
        return "Wednesday"
    elif (day == 4):
        return "Thursday"
    elif (day == 5):
        return "Friday"
    elif (day == 6):
        return "Saturday"
    elif (day == 7):
        return "Sunday"

def remove_selected_items(items):
    selectedItems = items.split('|')
    selectedItems = selectedItems[:-1]
    for item in selectedItems:
        sn_qty = item.split(",")
        sn = int(sn_qty[0])
        qty = int(sn_qty[1])
        update_row = AVAILABLE_ITEMS.row_values(sn + 1)

        prev_qty = int(update_row[3])
        prev_hold = int(update_row[4])
        new_hold = prev_hold - qty
        new_qty = prev_qty + qty
        AVAILABLE_ITEMS.update_cell(sn + 1, 4, new_qty)
        AVAILABLE_ITEMS.update_cell(sn + 1, 5, new_hold)

def day(update: Update, context: CallbackContext) -> str:
    # clear loading icon after pressing InLineButton
    update.callback_query.answer()

    daySelected = -1
    timeSelected = ""
    if("Please indicate the day that you are free in the upcoming week" in update['callback_query']['message']['text']):
        
        if(update['callback_query']['data'] == 'Exit'):
            # shld remove preprocessing if borrow
            if context.user_data['userChoice'] == USER_BORROW: 
                remove_selected_items(context.user_data['items'])
            
            update.callback_query.message.reply_text("Ok, good bye. Type /start to start over. ")
            return STATE_RETURN_TO_START

        daySelected = int(update['callback_query']['data'])
    elif ("Do you want to choose another timeslot?" in  update['callback_query']['message']['text']):
        if(update['callback_query']['data'] == YEP):
            return user(update, context)
    else:
        if(update['callback_query']['data'] == "Back"):
            return user(update,context)
        timeSelected = update['callback_query']['data']

    if(daySelected >= 0):
        #DATE OF CHOSEN DAY
        today = datetime.datetime.today().weekday() + 1
        diff = daySelected-today
        if(diff < 0):
            diff = 7 + diff

        ChosenDay = datetime.datetime.now() +timedelta(days=diff)

        #set up fixed available timeslots
        timings = []
        for i in range (8,21):
            if i < 10:
                booking_time = "0" + str(i) + ":00"
            else:
                booking_time = str(i) + ":00"
            
            timings.append(str(ChosenDay)[:10]+' T:'+booking_time)

        keyboard = []
        for time in timings:
            keyboard.append([InlineKeyboardButton(time[11:], callback_data= time)])
        
        keyboard.append([InlineKeyboardButton("Back", callback_data= "Back")])

        update.callback_query.message.reply_text(text=f"Please indicate the timeslot that you are free on {stringDay(daySelected)} to {context.user_data['userChoice']} your item(s).", reply_markup=InlineKeyboardMarkup(keyboard))

    elif (update['callback_query']['data'] == NAH):
        if(context.user_data['userChoice'] == USER_BORROW):
            to_append = []
            to_append = [context.user_data['full_name'], 
                        context.user_data['email'],
                        context.user_data['username'],
                        context.user_data['items'],
                        " ", 
                        context.user_data['timeSelected'],
                        'Pending Borrow',
                        ""]
            LOAN_LIST.append_row(to_append[:-1])
        else:
            loanRow = context.user_data['chosenRowToReturn']
            LOAN_LIST.update_cell(loanRow,STATUS_COL, "Pending Return")
            LOAN_LIST.update_cell(loanRow,RETURN_DATE_COL, context.user_data['timeSelected'])

        update.callback_query.message.reply_text(f"Your timeslot(s) on {context.user_data['timeSelected']} has been chosen. A MakerSpace student leader would be in contact with you soon.")
        return STATE_RETURN_TO_START
    
    else:
        context.user_data['timeSelected'] += timeSelected +", " 
        keyboard = [
            [InlineKeyboardButton("Yes", callback_data = YEP),
            InlineKeyboardButton("No", callback_data = NAH)]
        ]
        update.callback_query.message.reply_text(text=f"Do you want to choose another timeslot?", reply_markup=InlineKeyboardMarkup(keyboard))

################################ ADMIN FUNCTIONS ###########################################
def get_details(i):
    sn_quantity = LOANS[i]["S/N, Quantity"].split("|")
    details = ""
    item_quantity = ""
    for j in range(len(sn_quantity)):
        if len(sn_quantity[j].split(", ")) > 1:
            split_details = sn_quantity[j].split(", ")
            sn = split_details[0]
            item_name = AVAILABLE[int(sn) - 1]["Name"]
            quantity = split_details[1]
            item_quantity += (item_name + ", " + quantity + " ")
    details += "{:20}".format(item_quantity)
    details += "{:<10}".format(LOANS[i]["Name"])
    return details

    
def handle_loaning_details_choice(update: Update, context: CallbackContext) -> None:
    # After the user presses an inline button, Telegram clients will display a loading icon
    # Always call update.callback_query.answer() to clear the icon
    get_sheets()
    update.callback_query.answer()
    #details = "List of items on loan: \n"
    details = "{:<3}".format("*No.* ") + "{:<20}".format("*Item, Quantity*")
    details += "{:<10}".format("*Name*")
    details_len = len(details)
    # save task type so that we can use it later
    context.user_data["task_type"] = update.callback_query.data
    context.user_data["Loans"] = []
    count = 1
    if update.callback_query.data == TASK_ADMIN_TYPE_APPOINTMENTS: #allow admin to confirm appointments that have been placed
        context.user_data['state'] = "Appointment"
        details = "*List of pending appointments: \n*" + details
        details += "{:<15}".format("*Appointment Date* ") + "{:<10}".format(" *Type*") + "\n"
        details_len = len(details)
        for i in range(len(LOANS)):
            if ("Pending" in LOANS[i]["Status"]):
                details += "{:<3}".format("/" + str(count))
                count += 1
                details += get_details(i)
                context.user_data['Loans'].append(LOANS[i])
                if (LOANS[i]["Status"] == "Pending Borrow") :
                    appointment_details = format(LOANS[i]["Loan Date"])
                    details += "\n"+ "{:<15}".format(appointment_details)+ "{:<10}".format(" Borrow") + "\n"
                elif (LOANS[i]["Status"] == "Pending Return") :
                    appointment_details = format(LOANS[i]["Returned Date"])
                    details += "{:<15}".format(appointment_details) + "{:<10}".format(" Return") + "\n"

        if (len(details) == details_len):
            update.callback_query.message.reply_text(text="There are no pending Appointments! Type /start if you want to do something else!")
            return
        update.callback_query.message.reply_text(text=details, parse_mode=telegram.ParseMode.MARKDOWN)
        return STATE_ADMIN_CHOOSE_APPOINTMENT

    elif update.callback_query.data == TASK_ADMIN_TYPE_BORROW:
        context.user_data['state'] = "Borrow"
        details = "*List of upcoming loans: \n*" + details
        details += "\n"
        details_len = len(details)
        # take list of scheduled borrows and allow admin to select from there
        for i in range(len(LOANS)):
            if (LOANS[i]["Status"] == "Approved Borrow"):
                context.user_data['Loans'].append(LOANS[i])
                details += "{:<3}".format("/" + str(count))
                count += 1
                print(get_details(i))
                details += get_details(i) + "\n"
        if (len(details) == details_len):
            update.callback_query.message.reply_text(text="There are no pending Borrow Appointments! Type /start if you want to do something else!")
            return

    elif update.callback_query.data == TASK_ADMIN_TYPE_RETURN:
        context.user_data['state'] = "Return"
        details = "*List of loaned items: \n*" + details
        details += "*RFID Tags(s)*"
        details += "\n"
        details_len = len(details)
        # take list of borrowed items and allow admin to select from there
        for i in range(len(LOANS)):
            if (LOANS[i]["Status"] == "Approved Return"):
                context.user_data['Loans'].append(LOANS[i])
                details += "{:<3}".format("/" + str(count))
                count += 1
                details += get_details(i)
                for rfid in LOANS[i]["RFID"]:
                    details += str(rfid).replace("A", "0")
                details += "\n"
        if (len(details) == details_len):
            update.callback_query.message.reply_text(text="There are no pending Return Appointments! Type /start if you want to do something else!")
            return
    elif update.callback_query.data == TODAY_APPOINTMENTS:
        return find_today_appointments(update,context)
    else:
        update.callback_query.message.reply_text(f"Hmm idk what's {update.callback_query.data}, try again?")
        return STATE_CHOOSE_TASK_TYPE 
    
    update.callback_query.message.reply_text(text=details, parse_mode=telegram.ParseMode.MARKDOWN)
    return STATE_UPDATE_LOAN_SHEET

def handle_admin_choose_appointment(update: Update, context: CallbackContext) -> None:
    message = update.message.text
    choice = message[1:]
    # if reply is invalid, return to choose loaning details state
    if (not choice.isdigit()):
        update.message.reply_text("Invalid choice, please select the choice using the buttons above!")
        return STATE_ADMIN_CHOOSE_APPOINTMENT

    choice = int(choice)
    context.user_data['choice'] = choice
    context.user_data['position'] = 0
    context.user_data['row_info'] = ""

    for i in range(len(LOANS)):
        if (context.user_data['Loans'][choice - 1] == LOANS[i]):
            print(i)
            context.user_data['position'] = i
            break

    first_string = get_details(context.user_data['position'])
    first_string = "Appointment details: \n" + first_string + "\n" 
    
    appointment_type = ""

    if (LOANS[i]["Status"] == "Pending Borrow"):
        appointment_type = " (Borrow): \n"
        details = format(LOANS[i]["Loan Date"])
    elif (LOANS[i]["Status"] == "Pending Return"):
        appointment_type = " (Return): \n"
        details = format(LOANS[i]["Returned Date"])
    
    chosen_dates = details.split(", ")[:-1]
    count = 1
    splitted = ""
    for j in chosen_dates:
        splitted = splitted + "/" + str(count) + " " + j + "\n"
        count += 1
   
    keyboard = [[InlineKeyboardButton("Reject all", callback_data="Reject all")]]
    update.message.reply_text(first_string+ "\nChoose an appointment" + appointment_type + splitted, reply_markup=InlineKeyboardMarkup(keyboard))
    return STATE_ADMIN_SELECTED_APPOINTMENT_ONLY

def handle_reject_all(update: Update, context: CallbackContext) -> None:
    if(update.callback_query.data == "Reject all"):
        #if borrow, move to history, update available items
        rowInLoan = int(context.user_data['position']) + 2
        if(LOAN_LIST.cell(rowInLoan,STATUS_COL).value == "Pending Borrow"):
            itemsBorrowed = LOAN_LIST.cell(rowInLoan, ITEMS_COL).value.split('|')
            itemsBorrowed = itemsBorrowed[:-1] #remove last empty value
            for item in itemsBorrowed:
                splitItem = item.split(",")
                sn = int(splitItem[0])
                qty = int(splitItem[1])
                update_row = AVAILABLE_ITEMS.row_values(sn + 1)

                prevQty = int(AVAILABLE_ITEMS.cell(sn+1,4).value)
                prevHold =  int(AVAILABLE_ITEMS.cell(sn+1,5).value)
                print("PREV QTY " + str(prevQty))
                print("PREV HOLD " + str(prevHold))
                newHold = prevHold - qty
                newQty = prevQty + qty
                AVAILABLE_ITEMS.update_cell(sn + 1, 4, newQty)
                AVAILABLE_ITEMS.update_cell(sn + 1, 5, newHold)

            #move to history 
            row_values = LOAN_LIST.row_values(rowInLoan)
            print(row_values)
            row_values[STATUS_COL-1] = "Rejected Borrow"
            HISTORY_LIST.append_row(row_values)
            #remove from LOAN_LIST
            LOAN_LIST.delete_rows(rowInLoan)

        #if return, revert to Issued State
        elif(LOAN_LIST.cell(rowInLoan,STATUS_COL).value == "Pending Return"):
            LOAN_LIST.update_cell(rowInLoan,STATUS_COL, "Issued")
            LOAN_LIST.update_cell(rowInLoan,RETURN_DATE_COL, "")
    
    update.callback_query.message.reply_text("Ok appointment rejected")
    return STATE_RETURN_TO_START

def handle_admin_selected_appointment_only(update: Update, context: CallbackContext) -> None:
    # if reply is invalid, return to admin choose appointments state
    message = update.message.text
    print(message)
    choice = message[1:]
    if (not choice.isdigit()):
        update.callback_query.message.reply_text("Invalid choice, please select the choice using the buttons above!")
        return STATE_ADMIN_CHOOSE_APPOINTMENT
    
    choice = int(choice)
    if (LOANS[context.user_data['position']]["Status"] == "Pending Borrow"):
        details = format(LOANS[context.user_data['position']]["Loan Date"])
    elif (LOANS[context.user_data['position']]["Status"] == "Pending Return"):
        details = format(LOANS[context.user_data['position']]["Returned Date"])
    
    appointment_choices = details.split(", ")[:-1]
    print("appt choices")
    print(appointment_choices)
    selected_appointment = appointment_choices.pop(choice - 1)

    if (LOANS[context.user_data['position']]["Status"] == "Pending Borrow"):
        LOAN_LIST.update_cell(context.user_data['position'] + 2, 6, selected_appointment)
        LOAN_LIST.update_cell(context.user_data['position'] + 2, 7, "Approved Borrow")
        
    elif (LOANS[context.user_data['position']]["Status"] == "Pending Return"):
        LOAN_LIST.update_cell(context.user_data['position'] + 2, 8, selected_appointment)
        LOAN_LIST.update_cell(context.user_data['position'] + 2, 7, "Approved Return")

    update.message.reply_text("The appointment slot has been confirmed! Type /start if you want to do something else!")
    return STATE_RETURN_TO_START

def handle_update_loan_sheet(update: Update, context: CallbackContext) -> None:
    print("IN HANDLE UPDATE LOAN SHEET")
    message = update.message.text
    choice = message[1:]
    # if reply is invalid, return to choose loaning details state
    if (not choice.isdigit()):
        update.message.reply_text("Invalid choice, please select the choice using the buttons above!")
        return STATE_UPDATE_LOAN_SHEET
    choice = int(choice)
    context.user_data['choice'] = choice
    context.user_data['position'] = 0
    context.user_data['row_info'] = ""

    for i in range(len(LOANS)):
        if (context.user_data['Loans'][choice - 1] == LOANS[i]):
            print(i)
            context.user_data['position'] = i
            break
    details = get_details(context.user_data['position'])

    if (context.user_data['state'] == "Appointment"):
        context.user_data['type'] = context.user_data['Loans'][choice - 1]["Status"] 
        keyboard = [[
            InlineKeyboardButton("Approve", callback_data=TASK_ADMIN_TYPE_APPROVE_APPOINTMENT),
            InlineKeyboardButton("Reject", callback_data=TASK_ADMIN_TYPE_REJECT_APPOINTMENT),
            ]]
        update.message.reply_text("Appointment:\n" + details + "\nDo you want to accept or reject this appointment?", reply_markup=InlineKeyboardMarkup(keyboard))
        return STATE_ADMIN_EDIT_APPOINTMENT
        
    if (context.user_data['state'] == "Borrow"):
        keyboard = [[
            InlineKeyboardButton("Complete", callback_data=TASK_ADMIN_TYPE_COMPLETE_BORROW),
            InlineKeyboardButton("Cancel", callback_data=TASK_ADMIN_TYPE_CANCEL_BORROW),
            ]]
        update.message.reply_text("Borrow:\n" + details + "\nDo you want to complete or cancel this loan?", reply_markup=InlineKeyboardMarkup(keyboard))
        return STATE_ADMIN_EDIT_BORROW

    elif (context.user_data['state'] == "Return"):
        keyboard = [[
            InlineKeyboardButton("Yep", callback_data=YEP),
            InlineKeyboardButton("Nah", callback_data=NAH),
            ]]
        update.message.reply_text("Return:\n" + details + "\nDo you want to mark this loan as returned?", reply_markup=InlineKeyboardMarkup(keyboard))
        return STATE_ADMIN_EDIT_RETURN
    admin_options(update, context)
    return STATE_CHOOSE_LOANING_DETAILS

def handle_admin_edit_appointment(update: Update, context: CallbackContext) -> None:
    update.callback_query.answer()
    if update.callback_query.data == TASK_ADMIN_TYPE_APPROVE_APPOINTMENT:
        if (context.user_data['type'] == "Pending Borrow"):
            LOAN_LIST.update_cell(context.user_data['position'] + 2, 7, "Approved Borrow")
        elif (context.user_data['type'] == "Pending Return"):
            LOAN_LIST.update_cell(context.user_data['position'] + 2, 7, "Approved Return")
        update.callback_query.message.reply_text("Appointment Approved. Type /start if you want to do something else!")

    elif update.callback_query.data == TASK_ADMIN_TYPE_REJECT_APPOINTMENT:
        row_info = LOANS[context.user_data['Position']]

        if (context.user_data['type'] == "Pending Borrow"):
            row_info['Status'] = "Rejected Borrow"

        elif (context.user_data['type'] == "Pending Return"):
            row_info['Status'] = "Rejected Borrow"

        LOAN_LIST.delete_rows(context.user_data['position'] + 2)
        HISTORY_LIST.append_row(list(row_info.values()))

        arr = get_sn_quantity_array(context.user_data['position'])

        for i in range(len(arr)):
            current_hold = int(AVAILABLE[arr[i][0] - 1]["Hold"])
            current_quantity = int(AVAILABLE[arr[i][0] - 1]["Quantity"])
            quantity = int(arr[i][1])
            AVAILABLE_ITEMS.update_cell(int(arr[i][0]) + 1, 5, current_hold - quantity)
            AVAILABLE_ITEMS.update_cell(int(arr[i][0]) + 1, 4, current_quantity + quantity)
        
        update.callback_query.message.reply_text("Appointment Rejected. Type /start if you want to do something else!")
    
    return STATE_CHOOSE_LOANING_DETAILS

def handle_admin_edit_borrow(update: Update, context: CallbackContext) -> None:
    update.callback_query.answer()
    if update.callback_query.data == TASK_ADMIN_TYPE_COMPLETE_BORROW:
        context.user_data['loan details'] = get_sn_quantity_array(context.user_data['position'])
        context.user_data['loan quantity'] = get_total_loan_quantity(context.user_data['position'])
        update.callback_query.message.reply_text("You will need to enter " + str(context.user_data['loan quantity']) + " tag(s). Please enter them one by one.\nPlease key in the RFID Tag number(s): ")
        return STATE_WAITING_FOR_RFID_NUMBERS

    elif update.callback_query.data == TASK_ADMIN_TYPE_CANCEL_BORROW:
        row_info = LOANS[context.user_data['position']]
        row_info['Status'] = "Rejected Borrow"
        LOAN_LIST.delete_rows(context.user_data['position'] + 2)
        print(row_info.values())
        HISTORY_LIST.append_row(list(row_info.values()))
        update.callback_query.message.reply_text("Borrow Cancelled. Type /start if you want to do something else!")
    
    return STATE_CHOOSE_LOANING_DETAILS

def get_total_loan_quantity(position):
    sn_quantity = LOANS[position]["S/N, Quantity"].split("|")
    quantity = 0
    for j in range(len(sn_quantity)):
        if len(sn_quantity[j].split(", ")) > 1:
            quantity += int(sn_quantity[j].split(", ")[1])
    return quantity

def get_sn_quantity_array(position):
    sn_quantity = LOANS[position]["S/N, Quantity"].split("|")
    arr = []
    for j in range(len(sn_quantity)):
        if len(sn_quantity[j].split(", ")) > 1:
            sn = int(sn_quantity[j].split(", ")[0])
            quantity = int(sn_quantity[j].split(", ")[1])
            arr.append([sn, quantity])
    return arr

def get_rfid_from_admin(update: Update, context: CallbackContext) -> None:
    message = str(update.message.text)
    avail_rfids = []
    loan_details = context.user_data['loan details']
    for i in range(len(loan_details)):
        # loan_details[i] give me the item number
        print("\n\n\n\n\n")
        print(loan_details[i][0])
        if len(str(AVAILABLE[loan_details[i][0] - 1]["RFID Tag Number"])) > 10:
            rfids = AVAILABLE[loan_details[i][0] - 1]["RFID Tag Number"].split(", ")
            for rfid in rfids:
                avail_rfids.append(str(rfid).replace("A", "0"))
        else:
            avail_rfids.append(str(AVAILABLE[loan_details[i][0] - 1]["RFID Tag Number"]).replace("A", "0"))
    print(avail_rfids)
    if not message.isdigit() or not message in avail_rfids:
        print(message in avail_rfids)
        print(message.isdigit())
        update.message.reply_text("Please enter a valid RFID Tag!" + "\nHere is a list of valid RFIDs:\n" + str(avail_rfids))
        return STATE_WAITING_FOR_RFID_NUMBERS
    
    update.message.reply_text("Please wait while we process the tag.")
    index = int(message[:4])
    for loan in loan_details:
        if loan[0] == index:
            loan[1] -= 1
        if (loan[1] == 0):
            loan_details.remove(loan)
    print("\n\n\nhi")
    context.user_data['loan details'] = loan_details
    message = message.replace("0", "A", 1)
    current_rfids = str(AVAILABLE[index - 1]["RFID Tag Number"]).replace(message, "") 
    if (len(current_rfids) < 8):
        current_rfids = ""
    if (len(current_rfids) > 8):
        current_rfids = str(AVAILABLE[index - 1]["RFID Tag Number"]).replace(message + ", ", "")
    AVAILABLE_ITEMS.update_cell((index + 1), 2, current_rfids)
    current_rfids = str(LOANS[context.user_data['position']]["RFID"])
    if (len(current_rfids) <= 1):
        current_rfids = message
    else :
        current_rfids += ", " + message
    print(current_rfids)
    LOAN_LIST.update_cell(context.user_data['position'] + 2, 5, current_rfids)
    context.user_data['loan quantity'] -= 1

    if context.user_data['loan quantity'] == 0:
        LOAN_LIST.update_cell(context.user_data['position'] + 2, 7, "Issued")
        update.message.reply_text("Borrow Completed. Type /start if you want to do something else!")
        return STATE_CHOOSE_LOANING_DETAILS

    get_sheets()
    update.message.reply_text("Please key in next the RFID Tag number(s): ")

def handle_admin_edit_return(update: Update, context: CallbackContext) -> None:
    update.callback_query.answer()
    if (update.callback_query.data == NAH) :
        return STATE_CHOOSE_LOANING_DETAILS
    
    update.callback_query.message.reply_text("Please wait while we process the return.")
    row_info = LOANS[context.user_data['position']]
    LOAN_LIST.delete_rows(context.user_data['position'] + 2)
    print(row_info.values())
    HISTORY_LIST.append_row(list(row_info.values()))

    rfid = row_info["RFID"]
    rfid_list = []
    if (len(str(rfid)) > 8):
        rfid_list = rfid.split(", ")
    else:
        rfid_list.append(rfid)

    for i in range(len(rfid_list)):
        rfid_tag = rfid_list[i]
        item = str(rfid_tag).replace("A", "0")
        item_num = int(item[:4]) + 1
        # get the current data from the sheet
        current_rfid = str(AVAILABLE_ITEMS.cell(item_num,2).value)
        current_quantity = int(AVAILABLE_ITEMS.cell(item_num,4).value)
        current_hold = int(AVAILABLE_ITEMS.cell(item_num,5).value)

        if (len(current_rfid) > 8) :
            current_rfid += ", "

        # update the sheet
        logger.debug(current_rfid + ", " + str(item))
        current_rfid += str(rfid_tag)
        AVAILABLE_ITEMS.update_cell(item_num, 2, current_rfid)
        AVAILABLE_ITEMS.update_cell(item_num, 4, current_quantity + 1)
        AVAILABLE_ITEMS.update_cell(item_num, 5, current_hold - 1)
    update.callback_query.message.reply_text("Return Completed. Type /start if you want to do something else!")
    return STATE_CHOOSE_LOANING_DETAILS
    
def find_today_appointments(update: Update, context: CallbackContext) -> None:
    update.callback_query.message.reply_text("Retrieving appointments ...")
    keyboard = [[
        InlineKeyboardButton("Appointments", callback_data=TASK_ADMIN_TYPE_APPOINTMENTS),
        InlineKeyboardButton("Borrow", callback_data=TASK_ADMIN_TYPE_BORROW),
        InlineKeyboardButton("Return", callback_data=TASK_ADMIN_TYPE_RETURN),
        ],
        [InlineKeyboardButton("Today's appointment(s)", callback_data=TODAY_APPOINTMENTS)]]

    try:
        allLoanRecords =  LOAN_LIST.get_all_records()
        todayAppointments = {}
        #most recent incomplete loan record
        for index,cell in enumerate(allLoanRecords):
            row = int(index + 2)
            status_col = LOAN_LIST.cell(row,STATUS_COL).value
            if(status_col == "Approved Return"):
                rettime = LOAN_LIST.cell(row,RETURN_DATE_COL).value.strip()        
                if(rettime[:10] == date.today().strftime("%Y-%m-%d")):
                    todayAppointments[row] = ["Approved Return", rettime, LOAN_LIST.cell(row,ITEMS_COL).value]
            elif(status_col == "Approved Borrow"):
                bortime = LOAN_LIST.cell(row, RETURN_DATE_COL - 2).value.strip()
                if(bortime[:10] == date.today().strftime("%Y-%m-%d")):
                    todayAppointments[row] = ["Approved Borrow", bortime, LOAN_LIST.cell(row,ITEMS_COL).value]

        if(not todayAppointments):
            update.callback_query.message.reply_text(f"There is no appointments today. What do you want to do?", reply_markup=InlineKeyboardMarkup(keyboard))
            return STATE_CHOOSE_LOANING_DETAILS

        returnAppt = ""
        rtn = 1
        borrowAppt = ""
        borrow = 1
        for details in todayAppointments.values():
            if (details[0] == "Approved Return"):
                returnAppt += str(rtn) + ". Time: " + details[1][11:] + " Items: " + details[2] + "\n"
                rtn += 1
            else:
                borrowAppt += str(borrow) + ". Time: " + details[1][11:] + " Items: " + details[2] + "\n"
                borrow += 1
        
        toReturn = "Return Appointments:\n" + returnAppt + "\nBorrow Appointments:\n" + borrowAppt + "\n What do you want to do?"
        update.callback_query.message.reply_text(toReturn,  reply_markup=InlineKeyboardMarkup(keyboard)) 
        return STATE_CHOOSE_LOANING_DETAILS
    except Exception as e :
        print("EXCEPTION")
        print(e)
        keyboard = [[
            InlineKeyboardButton("Appointments", callback_data=TASK_ADMIN_TYPE_APPOINTMENTS),
            InlineKeyboardButton("Borrow", callback_data=TASK_ADMIN_TYPE_BORROW),
            InlineKeyboardButton("Return", callback_data=TASK_ADMIN_TYPE_RETURN),
            ],
            [InlineKeyboardButton("Today's appointment(s)", callback_data=TODAY_APPOINTMENTS)]]
        update.callback_query.message.reply_text("Some error owo", reply_markup=InlineKeyboardMarkup(keyboard))
        return STATE_CHOOSE_LOANING_DETAILS



############################ GENERAL COMMANDS ############################

def handle_stateless_callback_query(update: Update, context: CallbackContext):
    update.callback_query.answer()
    update.callback_query.message.reply_animation(animation="https://media.tenor.com/images/c6956678c2456adbcbaac55b57806240/tenor.gif", caption=f"idk what's happening, try doing /start to start?")

def handle_unknown_command(update: Update, context: CallbackContext):
    context.bot.send_message(chat_id=update.effective_chat.id, text="Invalid command.")

def handle_text_message_from_private_chats(update: Update, context: CallbackContext) -> None:
    update.message.reply_text(text=f"Type /start to begin!")

def main() -> None:
    # Create an updater object, and pass it the bot's token. 
    # The updater continuously fetches new updates from Telegram and passes them to the updater.dispatcher object.
    updater = telegram.ext.Updater(settings.TELEBOT["token"])

    # # Add handler for text messages (excluding commands), from private chats
    # updater.dispatcher.add_handler(MessageHandler(
    #     filters=Filters.text & ~Filters.command & Filters.chat_type.private, 
    #     callback=handle_text_message_from_private_chats))

    loaning_conversation_handler = ConversationHandler(
        entry_points=[
            CommandHandler(command="start", filters=Filters.chat_type.private, callback=start),
            CallbackQueryHandler(callback=handle_stateless_callback_query)
            ],
        states={
            #User verification
            STATE_VERIFY_USER_NAME: [MessageHandler(filters=Filters.text & ~Filters.command & Filters.chat_type.private, callback=handle_user_name)],
            STATE_VERIFY_USER_EMAIL: [MessageHandler(filters=Filters.text & ~Filters.command & Filters.chat_type.private, callback=handle_user_email)],

            #User options
            USER_CHOICE: [CallbackQueryHandler(callback=handle_user_choice)],
            USER_BORROW :[CallbackQueryHandler(callback=handle_user_loaning)],

            #User borrow
            STATE_CHOOSE_ITEM: [CallbackQueryHandler(callback=handle_user_loaning)],
            STATE_VERIFY_ITEM: [MessageHandler(filters=Filters.text & Filters.chat_type.private, callback=handle_verify_item)],
            STATE_VERIFY_QUANTITY: [MessageHandler(filters=Filters.text & Filters.chat_type.private, callback=handle_quantity)],
            STATE_LOAN_LOOP: [CallbackQueryHandler(callback=handle_loan_loop)],

            #User return
            CHOOSE_RETURN: [MessageHandler(filters=Filters.text & Filters.chat_type.private, callback=handle_choose_return)],

            #User cancel
            CHOOSE_CANCEL: [MessageHandler(filters=Filters.text & Filters.chat_type.private,callback=handle_choose_cancel)],


            #User appointment
            USER: [CallbackQueryHandler(callback=user)],
            DAY: [CallbackQueryHandler(callback=day)],
            DATE: [CallbackQueryHandler(callback=date)],

            #Admin selecting user appointment
            STATE_ADMIN_CHOOSE_APPOINTMENT: [MessageHandler(filters=Filters.text & Filters.chat_type.private, callback=handle_admin_choose_appointment)],
            STATE_ADMIN_SELECTED_APPOINTMENT_ONLY: [CallbackQueryHandler( callback=handle_reject_all), MessageHandler(filters=Filters.text & Filters.chat_type.private, callback=handle_admin_selected_appointment_only)],

            STATE_CHOOSE_LOANING_DETAILS: [CallbackQueryHandler(callback=handle_loaning_details_choice)],
            STATE_UPDATE_LOAN_SHEET: [MessageHandler(filters=Filters.text & Filters.chat_type.private, callback=handle_update_loan_sheet)],
            STATE_ADMIN_EDIT_APPOINTMENT: [CallbackQueryHandler(callback=handle_admin_edit_appointment)],
            STATE_ADMIN_EDIT_BORROW: [CallbackQueryHandler(callback=handle_admin_edit_borrow)], 
            STATE_ADMIN_EDIT_RETURN: [CallbackQueryHandler(callback=handle_admin_edit_return)],
            STATE_WAITING_FOR_RFID_NUMBERS: [MessageHandler(filters=Filters.text & Filters.chat_type.private, callback=get_rfid_from_admin)],
            
            TODAY_APPOINTMENTS : [CallbackQueryHandler(callback=find_today_appointments)],
            #End 
            STATE_RETURN_TO_START: [CallbackQueryHandler(callback=start)],
        },
        fallbacks=[CommandHandler(command="start", filters=Filters.chat_type.private, callback=start)],
    )

    # Add handler for loaning conversations for users
    updater.dispatcher.add_handler(loaning_conversation_handler)

    #add handler for the 

    # Add handler for commands that don't get handled by anything so far
    updater.dispatcher.add_handler(MessageHandler(filters=Filters.command, callback=handle_unknown_command))

    # Start the bot
    updater.start_polling()

    # Run the bot until you press Ctrl-C or the process receives SIGINT, SIGTERM or SIGABRT. 
    # This should be used most of the time, since start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()

if __name__ == "__main__":
    main()
