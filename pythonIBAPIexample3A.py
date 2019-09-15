# Here we go the ProfitMonk guys
# You would still need a 1.html file that we are using to set this file up while the profitmonk data download API is in the works
# Code inspired by multiple sources. Few of these are as follows - 
# https://stackoverflow.com/questions/54230044/how-to-obtain-contract-details-from-the-interactive-brokers-api
# https://stackoverflow.com/questions/57618971/how-do-i-get-my-accounts-positions-at-interactive-brokers-using-python-api/57813372#57813372
# https://qoppac.blogspot.com/2017/03/interactive-brokers-native-python-api.html
# https://groups.io/g/twsapi/
# https://qoppac.blogspot.com/2017/03/placing-orders-in-native-python-ib-api.html
# https://gist.github.com/robcarver17/c9b550c4cf335b3ab77eadd330f5c904


# Gist example of IB wrapper ...
#
# Download API from http://interactivebrokers.github.io/#
#
# Install python API code /IBJts/source/pythonclient $ python3 setup.py install
#
# Note: The test cases, and the documentation refer to a python package called IBApi,
#    but the actual package is called ibapi. Go figure.
#
# Get the latest version of the gateway:
# https://www.interactivebrokers.com/en/?f=%2Fen%2Fcontrol%2Fsystemstandalone-ibGateway.php%3Fos%3Dunix
#    (for unix: windows and mac users please find your own version)
#
# Run the gateway
#
# user: edemo
# pwd: demo123
#
# 

import sys
sys.path.append(r'C:/TWS API/') 
sys.path.append(r'C:/TWS API/source/pythonclient')
from ibapi.wrapper import EWrapper
from ibapi.client import EClient
from ibapi.contract import Contract as IBcontract
import shutil

from threading import Thread
import queue
from ibapi.order import Order
#from datetime import datetime, date, time
import datetime
import time
import pandas as pd
import numpy as np

DEFAULT_MARKET_DATA_ID=51
DEFAULT_GET_CONTRACT_ID=44

## marker for when queue is finished
FINISHED = object()
STARTED = object()
TIME_OUT = object()
class monkContract(IBcontract):
    def __init__(self,contractID,contractBuyTarget,contractTotalInvestment,contractSellTarget,contractNumToBuy):
        IBcontract.__init__(self)
        self.contractID = contractID
        self.contractBuyTarget = contractBuyTarget
        self.contractTotalInvestment = contractTotalInvestment
        self.contractSellTarget = contractSellTarget
        self.contractNumToBuy = contractNumToBuy


class finishableQueue(object):

    def __init__(self, queue_to_finish):

        self._queue = queue_to_finish
        self.status = STARTED

    def get(self, timeout):
        """
        Returns a list of queue elements once timeout is finished, or a FINISHED flag is received in the queue
        :param timeout: how long to wait before giving up
        :return: list of queue elements
        """
        contents_of_queue=[]
        finished=False

        while not finished:
            try:
                current_element = self._queue.get(timeout=timeout)
                if current_element is FINISHED:
                    finished = True
                    self.status = FINISHED
                else:
                    contents_of_queue.append(current_element)
                    ## keep going and try and get more data

            except queue.Empty:
                ## If we hit a time out it's most probable we're not getting a finished element any time soon
                ## give up and return what we have
                finished = True
                self.status = TIME_OUT


        return contents_of_queue

    def timed_out(self):
        return self.status is TIME_OUT


def _nan_or_int(x):
    if not np.isnan(x):
        return int(x)
    else:
        return x

class stream_of_ticks(list):
    """
    Stream of ticks
    """

    def __init__(self, list_of_ticks):
        super().__init__(list_of_ticks)

    def as_pdDataFrame(self):

        if len(self)==0:
            ## no data; do a blank tick
            return tick(datetime.datetime.now()).as_pandas_row()

        pd_row_list=[tick.as_pandas_row() for tick in self]
        pd_data_frame=pd.concat(pd_row_list)

        return pd_data_frame


class tick(object):
    """
    Convenience method for storing ticks
    Not IB specific, use as abstract
    """
    def __init__(self, timestamp, bid_size=np.nan, bid_price=np.nan,
                 ask_size=np.nan, ask_price=np.nan,
                 last_trade_size=np.nan, last_trade_price=np.nan,highForDay=np.nan,
                 lowForDay=np.nan,volumeForDay=np.nan,closeForDay=np.nan,
                 ignorable_tick_id=None):

        ## ignorable_tick_id keyword must match what is used in the IBtick class

        self.timestamp=timestamp
        self.bid_size=_nan_or_int(bid_size)
        self.bid_price=bid_price
        self.ask_size=_nan_or_int(ask_size)
        self.ask_price=ask_price
        self.last_trade_size=_nan_or_int(last_trade_size)
        self.last_trade_price=last_trade_price
        self.highForDay=_nan_or_int(highForDay)
        self.lowForDay=_nan_or_int(lowForDay)
        self.volumeForDay=_nan_or_int(volumeForDay)
        self.closeForDay=_nan_or_int(closeForDay)


    def __repr__(self):
        return self.as_pandas_row().__repr__()

    def as_pandas_row(self):
        """
        Tick as a pandas dataframe, single row, so we can concat together
        :return: pd.DataFrame
        """

        attributes=['bid_size','bid_price', 'ask_size', 'ask_price',
                    'last_trade_size', 'last_trade_price', 'highForDay',
                    'lowForDay', 'volumeForDay', 'closeForDay']

        self_as_dict=dict([(attr_name, getattr(self, attr_name)) for attr_name in attributes])

        return pd.DataFrame(self_as_dict, index=[self.timestamp])


class IBtick(tick):
    """
    Resolve IB tick categories
    """

    def __init__(self, timestamp, tickid, value):

        resolve_tickid=self.resolve_tickids(tickid)
        super().__init__(timestamp, **dict([(resolve_tickid, value)]))

    def resolve_tickids(self, tickid):

        tickid_dict=dict([("0", "bid_size"), ("1", "bid_price"), ("2", "ask_price"), ("3", "ask_size"),
                          ("4", "last_trade_price"), ("5", "last_trade_size"), ("6", "highForDay"), ("7","lowForDay"),
                          ("8", "volumeForDay"), ("9","closeForDay")])

        if str(tickid) in tickid_dict.keys():
            return tickid_dict[str(tickid)]
        else:
            # This must be the same as the argument name in the parent class
            return "ignorable_tick_id"

## marker to show a mergable object hasn't got any attributes
NO_ATTRIBUTES_SET=object()

class mergableObject(object):
    """
    Generic object to make it easier to munge together incomplete information about orders and executions
    """

    def __init__(self, id, **kwargs):
        """
        :param id: master reference, has to be an immutable type
        :param kwargs: other attributes which will appear in list returned by attributes() method
        """

        self.id=id
        attr_to_use=self.attributes()

        for argname in kwargs:
            if argname in attr_to_use:
                setattr(self, argname, kwargs[argname])
            else:
                print("Ignoring argument passed %s: is this the right kind of object? If so, add to .attributes() method" % argname)

    def attributes(self):
        ## should return a list of str here
        ## eg return ["thingone", "thingtwo"]
        return NO_ATTRIBUTES_SET

    def _name(self):
        return "Generic Mergable object - "

    def __repr__(self):

        attr_list = self.attributes()
        if attr_list is NO_ATTRIBUTES_SET:
            return self._name()

        return self._name()+" ".join([ "%s: %s" % (attrname, str(getattr(self, attrname))) for attrname in attr_list
                                                  if getattr(self, attrname, None) is not None])

    def merge(self, details_to_merge, overwrite=True):
        """
        Merge two things
        self.id must match
        :param details_to_merge: thing to merge into current one
        :param overwrite: if True then overwrite current values, otherwise keep current values
        :return: merged thing
        """

        if self.id!=details_to_merge.id:
            raise Exception("Can't merge details with different IDS %d and %d!" % (self.id, details_to_merge.id))

        arg_list = self.attributes()
        if arg_list is NO_ATTRIBUTES_SET:
            ## self is a generic, empty, object.
            ## I can just replace it wholesale with the new object

            new_object = details_to_merge

            return new_object

        new_object = deepcopy(self)

        for argname in arg_list:
            my_arg_value = getattr(self, argname, None)
            new_arg_value = getattr(details_to_merge, argname, None)

            if new_arg_value is not None:
                ## have something to merge
                if my_arg_value is not None and not overwrite:
                    ## conflict with current value, don't want to overwrite, skip
                    pass
                else:
                    setattr(new_object, argname, new_arg_value)

        return new_object


class orderInformation(mergableObject):
    """
    Collect information about orders
    master ID will be the orderID
    eg you'd do order_details = orderInformation(orderID, contract=....)
    """

    def _name(self):
        return "Order - "

    def attributes(self):
        return ['contract','order','orderstate','status',
                 'filled', 'remaining', 'avgFillPrice', 'permid',
                 'parentId', 'lastFillPrice', 'clientId', 'whyHeld',
                'mktCapPrice']

class list_of_mergables(list):
    """
    A list of mergable objects, like execution details or order information
    """


    def merged_dict(self):
        """
        Merge and remove duplicates of a stack of mergable objects with unique ID
        Essentially creates the union of the objects in the stack
        :return: dict of mergableObjects, keynames .id
        """

        ## We create a new stack of order details which will contain merged order or execution details
        new_stack_dict = {}

        for stack_member in self:
            id = stack_member.id

            if id not in new_stack_dict.keys():
                ## not in new stack yet, create a 'blank' object
                ## Note this will have no attributes, so will be replaced when merged with a proper object
                new_stack_dict[id] = mergableObject(id)

            existing_stack_member = new_stack_dict[id]

            ## add on the new information by merging
            ## if this was an empty 'blank' object it will just be replaced with stack_member
            new_stack_dict[id] = existing_stack_member.merge(stack_member)

        return new_stack_dict


    def blended_dict(self, stack_to_merge):
        """
        Merges any objects in new_stack with the same ID as those in the original_stack
        :param self: list of mergableObject or inheritors thereof
        :param stack_to_merge: list of mergableObject or inheritors thereof
        :return: dict of mergableObjects, keynames .id
        """

        ## We create a new dict stack of order details which will contain merged details

        new_stack = {}

        ## convert the thing we're merging into a dictionary
        stack_to_merge_dict = stack_to_merge.merged_dict()

        for stack_member in self:
            id = stack_member.id
            new_stack[id] = deepcopy(stack_member)

            if id in stack_to_merge_dict.keys():
                ## add on the new information by merging without overwriting
                new_stack[id] = stack_member.merge(stack_to_merge_dict[id], overwrite=False)

        return new_stack


## Just to make the code more readable

class list_of_execInformation(list_of_mergables):
    pass

class list_of_orderInformation(list_of_mergables):
    pass

class TestWrapper(EWrapper):
    """
    The wrapper deals with the action coming back from the IB gateway or TWS instance
    We override methods in EWrapper that will get called when this action happens, like currentTime
    Extra methods are added as we need to store the results in this object
    """

    def __init__(self):
        self._my_contract_details = {}
        self._my_market_data_dict = {}
        self._my_open_orders = queue.Queue()

    ## error handling code
    def init_error(self):
        error_queue=queue.Queue()
        self._my_errors = error_queue

    def get_error(self, timeout=5):
        if self.is_error():
            try:
                return self._my_errors.get(timeout=timeout)
            except queue.Empty:
                return None

        return None

    def is_error(self):
        an_error_if=not self._my_errors.empty()
        return an_error_if

    def error(self, id, errorCode, errorString):
        ## Overriden method
        errormsg = "IB error id %d errorcode %d string %s" % (id, errorCode, errorString)
        self._my_errors.put(errormsg)


    ## get contract details code
    def init_contractdetails(self, reqId):
        contract_details_queue = self._my_contract_details[reqId] = queue.Queue()

        return contract_details_queue

    def contractDetails(self, reqId, contractDetails):
        ## overridden method

        if reqId not in self._my_contract_details.keys():
            self.init_contractdetails(reqId)

        self._my_contract_details[reqId].put(contractDetails)

    def contractDetailsEnd(self, reqId):
        ## overriden method
        if reqId not in self._my_contract_details.keys():
            self.init_contractdetails(reqId)

        self._my_contract_details[reqId].put(FINISHED)

    # market data
    def init_market_data(self, tickerid):
        market_data_queue = self._my_market_data_dict[tickerid] = queue.Queue()

        return market_data_queue


    def get_time_stamp(self):
        ## Time stamp to apply to market data
        ## We could also use IB server time
        return datetime.datetime.now()


    def tickPrice(self, tickerid , tickType, price, attrib):
        ##overriden method

        ## For simplicity I'm ignoring these but they could be useful to you...
        ## See the documentation http://interactivebrokers.github.io/tws-api/md_receive.html#gsc.tab=0
        # attrib.canAutoExecute
        # attrib.pastLimit

        this_tick_data=IBtick(self.get_time_stamp(),tickType, price)
        #print("hahatickPrice")
        #print(tickType)
        #print("huhutickPrice")
        print("The value for ticktype {0} is {1}".format(tickType, price))
        self._my_market_data_dict[tickerid].put(this_tick_data)


    def tickSize(self, tickerid, tickType, size):
        ## overriden method

        this_tick_data=IBtick(self.get_time_stamp(), tickType, size)
        #print("hahatickSize")
        #print(tickType)
        #print("huhutickSize")
        self._my_market_data_dict[tickerid].put(this_tick_data)


    def tickString(self, tickerid, tickType, value):
        ## overriden method

        ## value is a string, make it a float, and then in the parent class will be resolved to int if size
        this_tick_data=IBtick(self.get_time_stamp(),tickType, float(value))
        self._my_market_data_dict[tickerid].put(this_tick_data)


    def tickGeneric(self, tickerid, tickType, value):
        ## overriden method

        this_tick_data=IBtick(self.get_time_stamp(),tickType, value)
        self._my_market_data_dict[tickerid].put(this_tick_data)

    def tickOptionComputation(self, tickerid, tickType, IV, delta, optPrice, pvDiv, gamma, vega, theta, undPrice):
        ## overriden method
        #print("hahatickSize")
        print("The value for tickType {0} is {1}, underlying Price is {2}".format(tickType, optPrice, undPrice))
        #print("huhutickSize")
        this_tick_data=IBtick(self.get_time_stamp(),tickType, optPrice)
        #self._my_market_data_dict[tickerid].put(this_tick_data)

    # orders
    def init_open_orders(self):
        open_orders_queue = self._my_open_orders = queue.Queue()

        return open_orders_queue


    def orderStatus(self, orderId, status, filled, remaining, avgFillPrice, permid,
                    parentId, lastFillPrice, clientId, whyHeld, mktCapPrice):

        order_details = orderInformation(orderId, status=status, filled=filled,
                 avgFillPrice=avgFillPrice, permid=permid,
                 parentId=parentId, lastFillPrice=lastFillPrice, clientId=clientId,
                                         whyHeld=whyHeld, mktCapPrice=mktCapPrice)

        self._my_open_orders.put(order_details)


    def openOrder(self, orderId, contract, order, orderstate):
        """
        Tells us about any orders we are working now
        overriden method
        """

        order_details = orderInformation(orderId, contract=contract, order=order, orderstate = orderstate)
        self._my_open_orders.put(order_details)


    def openOrderEnd(self):
        """
        Finished getting open orders
        Overriden method
        """

        self._my_open_orders.put(FINISHED)
    ## order ids
    def init_nextvalidid(self):

        orderid_queue = self._my_orderid_data = queue.Queue()

        return orderid_queue

    def nextValidId(self, orderId):
        """
        Give the next valid order id
        Note this doesn't 'burn' the ID; if you call again without executing the next ID will be the same
        If you're executing through multiple clients you are probably better off having an explicit counter
        """
        if getattr(self, '_my_orderid_data', None) is None:
            ## getting an ID which we haven't asked for
            ## this happens, IB server just sends this along occassionally
            self.init_nextvalidid()

        self._my_orderid_data.put(orderId)


class TestClient(EClient):
    """
    The client method
    We don't override native methods, but instead call them from our own wrappers
    """
    def __init__(self, wrapper):
        ## Set up with a wrapper inside
        EClient.__init__(self, wrapper)

        self._market_data_q_dict = {}

    def start_getting_IB_market_data(self, resolved_ibcontract, tickerid=DEFAULT_MARKET_DATA_ID):
        """
        Kick off market data streaming
        :param resolved_ibcontract: a Contract object
        :param tickerid: the identifier for the request
        :return: tickerid
        """

        self._market_data_q_dict[tickerid] = self.wrapper.init_market_data(tickerid)
        self.reqMarketDataType(2)
        self.reqMktData(tickerid, resolved_ibcontract, "", False, False, [])

        return tickerid

    def stop_getting_IB_market_data(self, tickerid):
        """
        Stops the stream of market data and returns all the data we've had since we last asked for it
        :param tickerid: identifier for the request
        :return: market data
        """

        ## native EClient method
        self.cancelMktData(tickerid)

        ## Sometimes a lag whilst this happens, this prevents 'orphan' ticks appearing
        time.sleep(5)

        market_data = self.get_IB_market_data(tickerid)

        ## output ay errors
        while self.wrapper.is_error():
            print(self.get_error())

        return market_data

    def get_IB_market_data(self, tickerid):
        """
        Takes all the market data we have received so far out of the stack, and clear the stack
        :param tickerid: identifier for the request
        :return: market data
        """

        ## how long to wait for next item
        MAX_WAIT_MARKETDATEITEM = 5
        market_data_q = self._market_data_q_dict[tickerid]

        market_data=[]
        finished=False

        while not finished:
            try:
                market_data.append(market_data_q.get(timeout=MAX_WAIT_MARKETDATEITEM))
            except queue.Empty:
                ## no more data
                finished=True

        return stream_of_ticks(market_data)

    def get_next_brokerorderid(self):
        """
        Get next broker order id
        :return: broker order id, int; or TIME_OUT if unavailable
        """
        ## Make a place to store the data we're going to return
        orderid_q = self.init_nextvalidid()

        self.reqIds(-1) # -1 is irrelevant apparently (see IB API docs)

        ## Run until we get a valid contract(s) or get bored waiting
        MAX_WAIT_SECONDS = 10
        try:
            brokerorderid = orderid_q.get(timeout=MAX_WAIT_SECONDS)
        except queue.Empty:
            print("Wrapper timeout waiting for broker orderid")
            brokerorderid = TIME_OUT

        while self.wrapper.is_error():
            print(self.get_error(timeout=MAX_WAIT_SECONDS))

        return brokerorderid

    def place_new_IB_order(self, ibcontract, order, orderid=None):
        """
        Places an order
        Returns brokerorderid
        """

        ## We can eithier supply our own ID or ask IB to give us the next valid one
        if orderid is None:
            print("Getting orderid from IB")
            orderid = self.get_next_brokerorderid()

            if orderid is TIME_OUT:
                raise Exception("I couldn't get an orderid from IB, and you didn't provide an orderid")

        print("Using order id of %d" % orderid)

        ## Note: It's possible if you have multiple traidng instances for orderids to be submitted out of sequence
        ##   in which case IB will break

        # Place the order
        self.placeOrder(
            orderid,  # orderId,
            ibcontract,  # contract,
            order  # order
        )

        return orderid

    def any_open_orders(self):
        """
        Simple wrapper to tell us if we have any open orders
        """

        return len(self.get_open_orders()) > 0

    def get_open_orders(self):
        """
        Returns a list of any open orders
        """

        ## store the orders somewhere
        open_orders_queue = finishableQueue(self.init_open_orders())

        ## You may prefer to use reqOpenOrders() which only retrieves orders for this client
        self.reqAllOpenOrders()

        ## Run until we get a terimination or get bored waiting
        MAX_WAIT_SECONDS = 5
        open_orders_list = list_of_orderInformation(open_orders_queue.get(timeout = MAX_WAIT_SECONDS))

        while self.wrapper.is_error():
            print(self.get_error())

        if open_orders_queue.timed_out():
            print("Exceeded maximum wait for wrapper to confirm finished whilst getting orders")

        ## open orders queue will be a jumble of order details, turn into a tidy dict with no duplicates
        open_orders_dict = open_orders_list.merged_dict()

        return open_orders_dict


class TestApp(TestWrapper, TestClient):
    def __init__(self, ipaddress, portid, clientid):
        TestWrapper.__init__(self)
        TestClient.__init__(self, wrapper=self)

        self.connect(ipaddress, portid, clientid)

        thread = Thread(target = self.run)
        thread.start()

        setattr(self, "_thread", thread)

        self.init_error()

def getSymbols(fileNameIn,algorithm):
    f = open(fileNameIn,'r')
    frame = pd.read_csv(fileNameIn)
    frame['year'] = pd.DatetimeIndex(frame['dateValue']).year
    frame['month'] = pd.DatetimeIndex(frame['dateValue']).month
    frame['day'] = pd.DatetimeIndex(frame['dateValue']).day
    yearToday = datetime.datetime.now().date().year
    monthToday = datetime.datetime.now().date().month
    dayToday = datetime.datetime.now().date().day
    yearToday = 2018
    monthToday = 1
    dayToday = 17
    #f = frame.query('month==@monthToday').query('year==@yearToday').query('day==@dayToday')
    f = frame.query('month==@monthToday').query('year==@yearToday')
    return(f)
    
#if __name__ == '__main__':
try:
    app
except NameError:
    app_exists = False
else:
    app_exists = True
if app_exists and app.isConnected():
    print ("app exists")
else:
    app = TestApp("127.0.0.1", 7496, 3)
#app = TestApp("127.0.0.1", 7496, 3)
#dateToday = datetime.datetime.now().date().strftime("%Y%m%d")
#fileNameIn = "c:/xampp/phpMyAdmin/upload/candidateSelection.txt";
#
#allSymbolFrame = getSymbols(fileNameIn,'SWINGPLUS')
#df_SWINGPLUS = allSymbolFrame[allSymbolFrame['algo']=='SWINGPLUS']
#df_MILESTONEPLUS = allSymbolFrame[allSymbolFrame['algo']=='MILESTONEPLUS']

## lets get prices for this
#ibcontract = IBcontract()
#ibcontract.secType = "FUT"
#ibcontract.lastTradeDateOrContractMonth="201812"
#ibcontract.symbol="GE"
#ibcontract.exchange="GLOBEX"
#WRITE CODE FOR - GET QUOTES FOR ALL STOCKS IN F
#WRITE CODE FOR - UPDATE TODAYS PRICE FOR ALL ACTIVE OPTIONS
#WRITE CODE FOR - UPDATE THE INFO FROM IB TO WEBPAGE
#file_allData = 'c:/xampp/phpMyAdmin/upload/master_allData.txt'
#fileCopy_allData = 'c:/xampp/phpMyAdmin/upload/'+dateToday+'_allData.txt'
#shutil.copyfile(file_allData,fileCopy_allData)
#f1 = open(file_allData,'a')
ibcontract = IBcontract()
ibcontract.secType = "OPT"
ibcontract.symbol="PPG"
ibcontract.exchange="CBOE"
ibcontract.symbol = "PPG"
ibcontract.secType = "OPT"
ibcontract.strike = 122
ibcontract.currency = "USD"
ibcontract.right = "C"
ibcontract.multiplier = 100
ibcontract.lastTradeDateOrContractMonth = "20191025"
tickerid = app.start_getting_IB_market_data(ibcontract)
#time.sleep(3)
market_data1 = app.get_IB_market_data(tickerid)
market_data1_as_df = market_data1.as_pdDataFrame()
#print(market_data1_as_df)
## stops the stream and returns all the data we've got so far
market_data2 = app.stop_getting_IB_market_data(tickerid)
## glue the data together
market_data2_as_df = market_data2.as_pdDataFrame()
all_market_data_as_df = pd.concat([market_data1_as_df, market_data2_as_df])
some_quotes = all_market_data_as_df.resample("1S").last()[["bid_size", "bid_price", "ask_price", "ask_size"]]
print(some_quotes.head(10))
bid_price = some_quotes['bid_price'].mean()
ask_price = some_quotes['ask_price'].mean()
mean_price = (bid_price + ask_price)/2
## Here goes the order code
order = Order()
order.action = "BUY"
order.orderType = "LMT"
order.totalQuantity = 1
order.lmtPrice = 0.05
order.tif = 'DAY'
order.transmit = True
orderid = app.place_new_IB_order(ibcontract, order, orderid=None)
open_orders = app.get_open_orders()
##app.disconnect()