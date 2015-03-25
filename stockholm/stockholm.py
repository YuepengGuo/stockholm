#coding:utf-8
import requests
import json
import datetime
import timeit
import time
import io
import os
import csv
## from pymongo import MongoClient
from multiprocessing.dummy import Pool as ThreadPool
from functools import partial

class Stockholm(object):

    def __init__(self, args):
        ## flag of if need to reload all stock data
        self.reload_data = args.reload_data
        ## flag of if need to generate portfolio
        self.gen_portfolio = args.gen_portfolio
        ## type of output file json/csv or both
        self.output_type = args.output_type
        ## portfolio testing date range(# of days)
        self.test_date_range = args.test_date_range
        ## stock data loading start date(e.g. 2014-09-14)
        self.start_date = args.start_date
        ## stock data loading end date
        self.end_date = args.end_date
        ## portfolio generating target date
        self.target_date = args.target_date
        ## thread number
        self.thread = args.thread
        
        ## data file store path
        if(args.store_path == 'USER_HOME/tmp/stockholm_export'):
            self.export_folder = os.path.expanduser('~') + '/tmp/stockholm_export'
        else:
            self.export_folder = args.store_path 

        ## for getting quote symbols
        self.all_quotes_url = 'http://money.finance.sina.com.cn/d/api/openapi_proxy.php'
        ## for loading quote data
        self.yql_url = 'http://query.yahooapis.com/v1/public/yql'
        ## export file name
        self.export_file_name = 'stockholm_export'

        self.index_array = ['000001.SS', '399001.SZ', '000300.SS']
        self.sh000001 = {'Symbol': '000001.SS', 'Name': '上证指数'}
        self.sz399001 = {'Symbol': '399001.SZ', 'Name': '深证成指'}
        self.sh000300 = {'Symbol': '000300.SS', 'Name': '沪深300'}
        ## self.sz399005 = {'Symbol': '399005.SZ', 'Name': '中小板指'}
        ## self.sz399006 = {'Symbol': '399006.SZ', 'Name': '创业板指'}
        
    def get_columns(self, quote):
        columns = []
        if(quote is not None):
            for key in quote.keys():
                if(key == 'Data'):
                    for data_key in quote['Data'][-1]:
                        columns.append("data." + data_key)
                else:
                    columns.append(key)
            columns.sort()
        return columns

    def get_profit_rate(self, price1, price2):
        if(price1 == 0):
            return None
        else:
            return round((price2-price1)/price1, 5)

    def get_MA(self, number_array):
        total = 0
        n = 0
        for num in number_array:
            if num is not None and num != 0:
                n += 1
                total += num
        return round(total/n, 3)

    class KDJ():
        def _avg(self, array):
            length = len(array)
            return sum(array)/length
        
        def _getMA(self, values, window):
            array = []
            x = window
            while x <= len(values):
                curmb = 50
                if(x-window == 0):
                    curmb = self._avg(values[x-window:x])
                else:
                    curmb = (array[-1]*2+values[x-1])/3
                array.append(round(curmb,3))
                x += 1
            return array
        
        def _getRSV(self, arrays):
            rsv = []
            x = 9
            while x <= len(arrays):
                high = max(map(lambda x: x['High'], arrays[x-9:x]))
                low = min(map(lambda x: x['Low'], arrays[x-9:x]))
                close = arrays[x-1]['Close']
                rsv.append((close-low)/(high-low)*100)
                t = arrays[x-1]['Date']
                x += 1
            return rsv
        
        def getKDJ(self, quote_data):
            if(len(quote_data) > 12):
                rsv = self._getRSV(quote_data)
                k = self._getMA(rsv,3)
                d = self._getMA(k,3)
                j = list(map(lambda x: round(3*x[0]-2*x[1],3), zip(k[2:], d)))
                
                for idx, data in enumerate(quote_data[0:12]):
                    data['KDJ_K'] = None
                    data['KDJ_D'] = None
                    data['KDJ_J'] = None
                for idx, data in enumerate(quote_data[12:]):
                    data['KDJ_K'] = k[2:][idx]
                    data['KDJ_D'] = d[idx]
                    if(j[idx] > 100):
                        data['KDJ_J'] = 100
                    elif(j[idx] < 0):
                        data['KDJ_J'] = 0
                    else:
                        data['KDJ_J'] = j[idx]
                
            return quote_data

    def load_all_quote_symbol(self):
        print("load_all_quote_symbol start..." + "\n")
        
        start = timeit.default_timer()

        all_quotes = []
        
        all_quotes.append(self.sh000001)
        all_quotes.append(self.sz399001)
        all_quotes.append(self.sh000300)
        ## all_quotes.append(self.sz399005)
        ## all_quotes.append(self.sz399006)
        
        try:
            count = 1
            while (count < 100):
                para_val = '[["hq","hs_a","",0,' + str(count) + ',500]]'
                r_params = {'__s': para_val}
                r = requests.get(self.all_quotes_url, params=r_params)
                if(len(r.json()[0]['items']) == 0):
                    break
                for item in r.json()[0]['items']:
                    quote = {}
                    code = item[0]
                    name = item[2]
                    ## convert quote code
                    if(code.find('sh') > -1):
                        code = code[2:] + '.SS'
                    elif(code.find('sz') > -1):
                        code = code[2:] + '.SZ'
                    ## convert quote code end
                    quote['Symbol'] = code
                    quote['Name'] = name
                    all_quotes.append(quote)
                count += 1
        except Exception as e:
            print("Error: Failed to load all stock symbol..." + "\n")
            print(e)
        
        print("load_all_quote_symbol end... time cost: " + str(round(timeit.default_timer() - start)) + "s" + "\n")
        return all_quotes

    def load_quote_info(self, quote, is_retry):
        print("load_quote_info start..." + "\n")
        
        start = timeit.default_timer()

        if(quote is not None and quote['Symbol'] is not None):
            yquery = 'select * from yahoo.finance.quotes where symbol = "' + quote['Symbol'].lower() + '"'
            r_params = {'q': yquery, 'format': 'json', 'env': 'http://datatables.org/alltables.env'}
            r = requests.get(self.yql_url, params=r_params)
            ## print(r.url)
            ## print(r.text)
            rjson = r.json()
            try:
                quote_info = rjson['query']['results']['quote']
                quote['LastTradeDate'] = quote_info['LastTradeDate']
                quote['LastTradePrice'] = quote_info['LastTradePriceOnly']
                quote['PreviousClose'] = quote_info['PreviousClose']
                quote['Open'] = quote_info['Open']
                quote['DaysLow'] = quote_info['DaysLow']
                quote['DaysHigh'] = quote_info['DaysHigh']
                quote['Change'] = quote_info['Change']
                quote['ChangeinPercent'] = quote_info['ChangeinPercent']
                quote['Volume'] = quote_info['Volume']
                quote['MarketCap'] = quote_info['MarketCapitalization']
                quote['StockExchange'] = quote_info['StockExchange']
                
            except Exception as e:
                print("Error: Failed to load stock info... " + quote['Symbol'] + "/" + quote['Name'] + "\n")
                print(e + "\n")
                if(not is_retry):
                    time.sleep(1)
                    load_quote_info(quote, True) ## retry once for network issue
            
        ## print(quote)
        print("load_quote_info end... time cost: " + str(round(timeit.default_timer() - start)) + "s" + "\n")
        return quote

    def load_all_quote_info(self, all_quotes):
        print("load_all_quote_info start...")
        
        start = timeit.default_timer()
        for idx, quote in enumerate(all_quotes):
            print("#" + str(idx + 1))
            load_quote_info(quote, False)

        print("load_all_quote_info end... time cost: " + str(round(timeit.default_timer() - start)) + "s")
        return all_quotes

    def load_quote_data(self, quote, start_date, end_date, is_retry, counter):
        ## print("load_quote_data start..." + "\n")
        
        start = timeit.default_timer()

        if(quote is not None and quote['Symbol'] is not None):        
            yquery = 'select * from yahoo.finance.historicaldata where symbol = "' + quote['Symbol'].upper() + '" and startDate = "' + start_date + '" and endDate = "' + end_date + '"'
            r_params = {'q': yquery, 'format': 'json', 'env': 'http://datatables.org/alltables.env'}
            r = requests.get(self.yql_url, params=r_params)
            ## print(r.url)
            ## print(r.text)
            rjson = r.json()
            try:
                quote_data = rjson['query']['results']['quote']
                quote_data.reverse()
                quote['Data'] = quote_data
                if(not is_retry):
                    counter.append(1)          
                
            except:
                print("Error: Failed to load stock data... " + quote['Symbol'] + "/" + quote['Name'] + "\n")
                if(not is_retry):
                    time.sleep(2)
                    self.load_quote_data(quote, start_date, end_date, True, counter) ## retry once for network issue
        
            print("load_quote_data " + quote['Symbol'] + "/" + quote['Name'] + " end..." + "\n")
            ## print("time cost: " + str(round(timeit.default_timer() - start)) + "s." + "\n")
            ## print("total count: " + str(len(counter)) + "\n")
        return quote

    def load_all_quote_data(self, all_quotes, start_date, end_date):
        print("load_all_quote_data start..." + "\n")
        
        start = timeit.default_timer()

        counter = []
        mapfunc = partial(self.load_quote_data, start_date=start_date, end_date=end_date, is_retry=False, counter=counter)
        pool = ThreadPool(self.thread)
        pool.map(mapfunc, all_quotes) ## multi-threads executing
        pool.close() 
        pool.join()

        print("load_all_quote_data end... time cost: " + str(round(timeit.default_timer() - start)) + "s" + "\n")
        return all_quotes

    def data_process(self, all_quotes):
        print("data_process start..." + "\n")
        
        kdj = self.KDJ()
        start = timeit.default_timer()
        
        for quote in all_quotes:
            if('Data' in quote):
                try:
                    temp_data = []
                    for quote_data in quote['Data']:
                        if(quote_data['Volume'] != '000' or quote_data['Symbol'] in self.index_array):
                            d = {}
                            d['Open'] = float(quote_data['Open'])
                            ## d['Adj_Close'] = float(quote_data['Adj_Close'])
                            d['Close'] = float(quote_data['Close'])
                            d['High'] = float(quote_data['High'])
                            d['Low'] = float(quote_data['Low'])
                            d['Volume'] = int(quote_data['Volume'])
                            d['Date'] = quote_data['Date']
                            temp_data.append(d)
                    quote['Data'] = temp_data
                except KeyError as e:
                    print("Key Error")
                    print(e)
                    print(quote)

        ## calculate Change / 10 Day MA
        for quote in all_quotes:
            if('Data' in quote):
                try:
                    last_10_array = []
                    for i, quote_data in enumerate(quote['Data']):
                        if(i > 0):
                            quote_data['Change'] = self.get_profit_rate(quote['Data'][i-1]['Close'], quote_data['Close'])
                            quote_data['Vol_Change'] = self.get_profit_rate(quote['Data'][i-1]['Volume'], quote_data['Volume'])                        
                        else:
                            quote_data['Change'] = None
                            quote_data['Vol_Change'] = None
                            
                    for i, quote_data in enumerate(quote['Data']):
                        last_10_array.append(quote_data['Close'])
                        if(i < 9):
                            quote_data['MA_10'] = None
                            continue
                        if(len(last_10_array) == 10):
                            last_10_array.pop(0)
                        quote_data['MA_10'] = self.get_MA(last_10_array)
                        
                except KeyError as e:
                    print("Key Error")
                    print(e)
                    print(quote)

        ## calculate KDJ
        for quote in all_quotes:
            if('Data' in quote):
                try:
                    kdj.getKDJ(quote['Data'])
                except KeyError as e:
                    print("Key Error")
                    print(e)
                    print(quote)

        print("data_process end... time cost: " + str(round(timeit.default_timer() - start)) + "s" + "\n")

    def data_export(self, all_quotes, export_type_array, file_name):
        
        start = timeit.default_timer()
        directory = self.export_folder
        if(file_name is None):
            file_name = self.export_file_name
        if not os.path.exists(directory):
            os.makedirs(directory)

        if(all_quotes is None or len(all_quotes) == 0):
            print("no data to export...")
        
        if('json' in export_type_array):
            print("start export to JSON file...")
            f = io.open(directory + '/' + file_name + '.json', 'w', encoding='utf-8')
            json.dump(all_quotes, f, ensure_ascii=False)
            
        if('csv' in export_type_array):
            print("start export to CSV file...")
            columns = []
            if(all_quotes is not None and len(all_quotes) > 0):
                columns = self.get_columns(all_quotes[0])
            writer = csv.writer(open(directory + '/' + file_name + '.csv', 'w', encoding='gbk'))
            writer.writerow(columns)

            for quote in all_quotes:
                if('Data' in quote):
                    for quote_data in quote['Data']:
                        try:
                            line = []
                            for column in columns:
                                if(column.find('data.') > -1):
                                    if(column[5:] in quote_data):
                                        line.append(quote_data[column[5:]])
                                else:
                                    line.append(quote[column])
                            writer.writerow(line)
                        except Exception as e:
                            print(e)
                            print("write csv error: " + quote)
            
        if('mongo' in export_type_array):
            print("start export to MongoDB...")
            
        print("export is complete... time cost: " + str(round(timeit.default_timer() - start)) + "s" + "\n")

    def file_data_load(self):
        print("file_data_load start..." + "\n")
        
        start = timeit.default_timer()
        directory = self.export_folder
        file_name = self.export_file_name
        
        all_quotes_data = []
        f = io.open(directory + '/' + file_name + '.json', 'r', encoding='utf-8')
        json_str = f.readline()
        all_quotes_data = json.loads(json_str)
        
        print("file_data_load end... time cost: " + str(round(timeit.default_timer() - start)) + "s" + "\n")
        return all_quotes_data

    def check_date(self, all_quotes, date):
        
        is_date_valid = False
        for quote in all_quotes:
            if(quote['Symbol'] in self.index_array):
                for quote_data in quote['Data']:
                    if(quote_data['Date'] == date):
                        is_date_valid = True
        if not is_date_valid:
            print(date + " is not valid...")
        return is_date_valid

    def quote_pick(self, all_quotes, target_date):
        print("quote_pick start..." + "\n")
        
        start = timeit.default_timer()

        results = []
        data_issue_count = 0
        
        for quote in all_quotes:
            try:
                if(quote['Symbol'] in self.index_array):
                    results.append(quote)
                    continue
                
                target_idx = None
                for idx, quote_data in enumerate(quote['Data']):
                    if(quote_data['Date'] == target_date):
                        target_idx = idx
                if(target_idx is None):
                    ## print(quote['Name'] + " data is not available at this date..." + "\n")
                    data_issue_count+=1
                    continue
                
                ## pick logic ##
                kdj_j_day_0 = quote['Data'][target_idx]['KDJ_J']
                kdj_j_day_m_1 = quote['Data'][target_idx-1]['KDJ_J']
                kdj_j_day_m_2 = quote['Data'][target_idx-2]['KDJ_J']
                kdj_j_day_m_3 = quote['Data'][target_idx-3]['KDJ_J']
                change_day_0 = quote['Data'][target_idx]['Change']
                change_day_m_1 = quote['Data'][target_idx-1]['Change']
                change_day_m_2 = quote['Data'][target_idx-2]['Change']
                change_day_m_3 = quote['Data'][target_idx-3]['Change']
                vol_change_day_0 = quote['Data'][target_idx]['Change']
                vol_change_day_m_1 = quote['Data'][target_idx-1]['Vol_Change']
                vol_change_day_m_2 = quote['Data'][target_idx-2]['Vol_Change']
                vol_change_day_m_3 = quote['Data'][target_idx-3]['Vol_Change']
                            
                if(kdj_j_day_0 is not None):
                    if(kdj_j_day_m_3 is not None):
                        if(kdj_j_day_m_2 is not None and kdj_j_day_m_3 < kdj_j_day_m_2):
                            if(kdj_j_day_m_1 is not None and 50 < kdj_j_day_m_1 < 80 and kdj_j_day_m_2 < kdj_j_day_m_1):
                                if(kdj_j_day_0 < kdj_j_day_m_1):
                                    results.append(quote)
                                    continue
                    
                    if(kdj_j_day_m_2 is not None and kdj_j_day_m_2 < 20):
                        if(kdj_j_day_m_1 is not None and kdj_j_day_m_1 < 20):
                            if(kdj_j_day_0 - kdj_j_day_m_1 >= 40):
                                if(quote['Data'][target_idx]['Vol_Change'] >= 1):
                                    if(quote['Data'][target_idx]['MA_10']*1.05 > quote['Data'][target_idx]['Close']):
                                        results.append(quote)
                                        continue
                                        
                    if(kdj_j_day_m_2 is not None):
                        if(kdj_j_day_m_1 is not None and kdj_j_day_m_2-kdj_j_day_m_1 >= 20):
                            if(kdj_j_day_0 - kdj_j_day_m_1 >= 20):
                                if(kdj_j_day_m_1 < 50):
                                    if(quote['Data'][target_idx]['Vol_Change'] <= 1):
                                        results.append(quote)
                                        continue
                                    
                ## pick logic end ##
                
            except KeyError as e:
                ## print("KeyError: " + quote['Name'] + " data is not available..." + "\n")
                data_issue_count+=1
                
        print("quote_pick end... time cost: " + str(round(timeit.default_timer() - start)) + "s" + "\n")
        print(str(data_issue_count) + " quotes of data is not available...")
        return results

    def profit_test(self, selected_quotes, target_date):
        print("profit_test start..." + "\n")
        
        start = timeit.default_timer()
        
        results = []
        INDEX = None
        INDEX_idx = 0

        for quote in selected_quotes:
            if(quote['Symbol'] == self.sh000300['Symbol']):
                INDEX = quote
                for idx, quote_data in enumerate(quote['Data']):
                    if(quote_data['Date'] == target_date):
                        INDEX_idx = idx
                break
        
        for quote in selected_quotes:
            target_idx = None
            
            if(quote['Symbol'] in self.index_array):
                continue
            
            for idx, quote_data in enumerate(quote['Data']):
                if(quote_data['Date'] == target_date):
                    target_idx = idx
            if(target_idx is None):
                print(quote['Name'] + " data is not available for testing..." + "\n")
                continue
            
            test = {}
            test['Name'] = quote['Name']
            test['Symbol'] = quote['Symbol']
            test['KDJ_K'] = quote['Data'][target_idx]['KDJ_K']
            test['KDJ_D'] = quote['Data'][target_idx]['KDJ_D']
            test['KDJ_J'] = quote['Data'][target_idx]['KDJ_J']
            test['Close'] = quote['Data'][target_idx]['Close']
            test['Change'] = quote['Data'][target_idx]['Change']
            test['Vol_Change'] = quote['Data'][target_idx]['Vol_Change']
            test['MA_10'] = quote['Data'][target_idx]['MA_10']
            test['Data'] = [{}]
            
            if(target_idx+1 >= len(quote['Data'])):
                print(quote['Name'] + " data is not available for 1 day testing..." + "\n")
                results.append(test)
                continue

            day_1_profit = self.get_profit_rate(quote['Data'][target_idx]['Close'], quote['Data'][target_idx+1]['Close'])
            test['Data'][0]['Day_1_Profit'] = day_1_profit
            day_1_INDEX_change = self.get_profit_rate(INDEX['Data'][INDEX_idx]['Close'], INDEX['Data'][INDEX_idx+1]['Close'])
            test['Data'][0]['Day_1_INDEX_Change'] = day_1_INDEX_change
            test['Data'][0]['Day_1_Differ'] = day_1_profit-day_1_INDEX_change
            
            if(target_idx+3 >= len(quote['Data'])):
                print(quote['Name'] + " data is not available for 3 days testing..." + "\n")
                results.append(test)
                continue
            
            day_3_profit = self.get_profit_rate(quote['Data'][target_idx]['Close'], quote['Data'][target_idx+3]['Close'])
            test['Data'][0]['Day_3_Profit'] = day_3_profit
            day_3_INDEX_change = self.get_profit_rate(INDEX['Data'][INDEX_idx]['Close'], INDEX['Data'][INDEX_idx+3]['Close'])
            test['Data'][0]['Day_3_INDEX_Change'] = day_3_INDEX_change
            test['Data'][0]['Day_3_Differ'] = day_3_profit-day_3_INDEX_change

            if(target_idx+5 >= len(quote['Data'])):
                print(quote['Name'] + " data is not available for 5 days testing..." + "\n")
                results.append(test)
                continue
            
            day_5_profit = self.get_profit_rate(quote['Data'][target_idx]['Close'], quote['Data'][target_idx+5]['Close'])
            test['Data'][0]['Day_5_Profit'] = day_5_profit
            day_5_INDEX_change = self.get_profit_rate(INDEX['Data'][INDEX_idx]['Close'], INDEX['Data'][INDEX_idx+5]['Close'])
            test['Data'][0]['Day_5_INDEX_Change'] = day_5_INDEX_change
            test['Data'][0]['Day_5_Differ'] = day_5_profit-day_5_INDEX_change
            
            if(target_idx+9 >= len(quote['Data'])):
                print(quote['Name'] + " data is not available for 9 days testing..." + "\n")
                results.append(test)
                continue
            
            day_9_profit = self.get_profit_rate(quote['Data'][target_idx]['Close'], quote['Data'][target_idx+9]['Close'])
            test['Data'][0]['Day_9_Profit'] = day_9_profit
            day_9_INDEX_change = self.get_profit_rate(INDEX['Data'][INDEX_idx]['Close'], INDEX['Data'][INDEX_idx+9]['Close'])
            test['Data'][0]['Day_9_INDEX_Change'] = day_9_INDEX_change
            test['Data'][0]['Day_9_Differ'] = day_9_profit-day_9_INDEX_change
            
            results.append(test)
            
        print("profit_test end... time cost: " + str(round(timeit.default_timer() - start)) + "s" + "\n")
        return results

    def data_load(self, start_date, end_date, output_types):
        all_quotes = self.load_all_quote_symbol()
        print("total " + str(len(all_quotes)) + " quotes are loaded..." + "\n")
        all_quotes = all_quotes
        ## self.load_all_quote_info(all_quotes)
        self.load_all_quote_data(all_quotes, start_date, end_date)
        self.data_process(all_quotes)
        
        self.data_export(all_quotes, output_types, None)

    def data_test(self, target_date, test_range, output_types):
        all_quotes = self.file_data_load()
        target_date_time = datetime.datetime.strptime(target_date, "%Y-%m-%d")
        for i in range(test_range):
            date = (target_date_time - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
            is_date_valid = self.check_date(all_quotes, date)
            if is_date_valid:
                selected_quotes = self.quote_pick(all_quotes, date)
                res = self.profit_test(selected_quotes, date)
                self.data_export(res, output_types, 'result_' + date)

    def run(self):
        ## output types
        output_types = []
        if(self.output_type == "json"):
            output_types.append("json")
        elif(self.output_type == "csv"):
            output_types.append("csv")
        elif(self.output_type == "all"):
            output_types = ["json", "csv"]
            
        ## loading stock data
        if(self.reload_data == 'Y'):
            self.data_load(self.start_date, self.end_date, output_types)
            
        ## test & generate portfolio
        if(self.gen_portfolio == 'Y'): 
            self.data_test(self.target_date, self.test_date_range, output_types)


