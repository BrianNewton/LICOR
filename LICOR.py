# Python v3.10.1
# matplotlib v3.5.1
# XlsxWriter v3.0.2

# Tool used to process raw LICOR data
# Enables users to prune raw data for ebullition events or inconsistent results

# For issues, suggestions or concerns contact btnewton@uwaterloo.ca


from math import floor
import math
import sys
import tkinter
import re
import matplotlib.pyplot as plt
import matplotlib.lines as lines
import os
import tkinter
import tkinter.filedialog
import xlsxwriter


# draggable lines for user cuts
class draggable_lines:
    def __init__(self, ax, h_or_v, start_coordinate, x_bounds, y_bounds):
        self.ax = ax
        self.c = ax.get_figure().canvas
        self.h_or_v = h_or_v
        self.x_bounds = x_bounds
        self.y_bounds = y_bounds

        if h_or_v == 'v':
            self.x = [start_coordinate, start_coordinate]
            self.y = y_bounds
            self.line = lines.Line2D(self.x, self.y, color='r', picker=5)
        elif h_or_v == 'h':
            self.x = x_bounds
            self.y = [start_coordinate,start_coordinate]
            self.line = lines.Line2D(self.x, self.y, color='g', picker=5)

        self.ax.add_line(self.line)
        self.c.draw_idle()
        self.sid = self.c.mpl_connect('pick_event', self.clickonline)

    def clickonline(self, event):
        if event.artist == self.line:
            self.follower = self.c.mpl_connect("motion_notify_event", self.followmouse)
            self.releaser = self.c.mpl_connect("button_press_event", self.releaseonclick)

    def followmouse(self, event):
        if self.h_or_v == 'v':
            if event.xdata and self.x_bounds[0] <= event.xdata <= self.x_bounds[1]:
                self.line.set_xdata([event.xdata, event.xdata])
        else:
            if event.ydata and self.y_bounds[0] <= event.ydata <= self.y_bounds[1]:
                self.line.set_ydata([event.ydata, event.ydata])
        self.c.draw_idle()

    def releaseonclick(self, event):
        if self.h_or_v == 'v':
            self.x = self.line.get_xdata()
        else:
            self.y = self.line.get_ydata()
        self.c.mpl_disconnect(self.releaser)
        self.c.mpl_disconnect(self.follower)


# Flux object
class Flux:
    def __init__(self, name, light_or_dark, start_time, end_time, start_temp, end_temp):

        light_regex = r"L|l|Light|light"
        dark_regex = r"D|d|Dark|dark"

        if re.search(light_regex, light_or_dark):
            self.name = name + " " + "light"    # flux light name
        elif re.search(dark_regex, light_or_dark):
            self.name = name + " " + "dark"     # flux dark name
        else:
            self.name = name    # neither light nor dark name
            
        self.start_time = start_time    # LICOR flux start time
        self.end_time = end_time        # LICOR flux end time
        self.temp = (float(start_temp) + float(end_temp))/2 + 273.15    # average of start and end air temperature

        self.original_length = 0    # original length of flux data
        self.data_loss = 0          # total percent of data set pruned

        self.times = []             # LICOR times
        self.pruned_times = []      # pruned LICOR times
        self.time_offsets = []      # offsets for each LICOR time index

        self.CH4 = []               # LICOR gas concentrations
        self.pruned_CH4 = []        # pruned LICOR concentrations
        self.CH4_offsets = []       # offsets for each LICOR concentration index

        self.cuts = []      # every user data cut
            
        self.RSQ = 0        # R^2 for final rate calculation
        self.RoC = 0        # rate of change (concentration/minute)
        self.flux = 0       # final calculated flux


# parses raw LICOR data, as well as field data into flux objects
def input_data(field_data, licor_data, CO2_or_CH4):
    fluxes = [] # set of flux objects

    # find relevant data indices in field data file
    collar_regex = r"collar$|name"
    l_or_d_regex = r"light[ -_]or[ -_]dark"
    start_time_regex = r"start[ -_]time"
    end_time_regex = r"end[ -_]time"
    start_temp_regex = r"start[ -_]temp"
    end_temp_regex = r"end[ -_]temp"

    collar_index = 0
    l_or_d_index = 1
    start_time_index = 2
    end_time_index = 3
    start_temp_index = 4
    end_temp_index = 5

    # for each flux, obtain from field data file the name, start and end times
    f = open(field_data, "r")
    x = next(f).split(",")
    for i in range(len(x)):
        x[i] = x[i].strip(' \t\n\r')
        if re.search(collar_regex, x[i], re.IGNORECASE):
            collar_index = i
        if re.search(l_or_d_regex, x[i], re.IGNORECASE):
            l_or_d_index = i
        if re.search(start_time_regex, x[i], re.IGNORECASE):
            start_time_index = i 
        if re.search(end_time_regex, x[i], re.IGNORECASE):
            end_time_index = i
        if re.search(start_temp_regex, x[i], re.IGNORECASE):
            start_temp_index = i
        if re.search(end_temp_regex, x[i], re.IGNORECASE):
            end_temp_index = i

    
    for line in f:
        x = line.split(",")
        for i in range(len(x)):
            x[i] = x[i].strip(' \t\n\r')
        fluxes.append(Flux(x[collar_index], x[l_or_d_index], x[start_time_index], x[end_time_index], x[start_temp_index], x[end_temp_index]))
    f.close()

    # use the raw LICOR data as well as the parsed field data to obtain unpruned sets of times and concentrations for each flux
    f = open(licor_data, "r")
    next(f), next(f), next(f), next(f), next(f), next(f), next(f)
    i = 0
    in_flux = 0
    times = []
    CH4 = []
    if CO2_or_CH4.lower() == 'co2':
        index = 8
    else:
        index = 9

    # go line by line in LICOR data, adding relevant times and concentrations to approrpiate fluxes
    for flux in fluxes:
        f.seek(6)
        print(flux.name)
        for line in f:
            x = line.split(",")
            for k in range(len(x)):
                x[k] = x[k].strip(' \t\n\r')
            if in_flux == 0:    # if current line in LICOR data isn't in a flux, check to see if it's the start time of the next flux
                if x[6] == flux.start_time:
                    in_flux = 1
                    start_seconds = float(x[1])
                    times.append(float(x[1]) - start_seconds)
                    CH4.append(float(x[index]))
            elif in_flux == 1:  # if current line in LICOR data is in a flux, append the time and gas concentration to flux
                times.append(float(x[1]) - start_seconds)
                CH4.append(float(x[index]))
                if x[6] == flux.end_time:  # if current line in LICOR data is the end time of the current flux, finalize times and concentrations sets and stop
                    flux.times = times
                    flux.CH4 = CH4
                    flux.pruned_times = times
                    flux.pruned_CH4 = CH4
                    flux.original_length = len(times)

                    times = []
                    CH4 = []
                    in_flux = 0
                    start_seconds = 0 
                    continue
    f.close()
    return fluxes


# process button press for plot
def on_press(event, i, fluxes, line_L, line_R, fig, ax, cid):
    sys.stdout.flush()

    # if enter key pressed, cut data according to currently set cut bounds
    if event.key == 'enter':

        # get cut indices from left and right lines
        time_L = floor(line_L.x[0])
        time_R = floor(line_R.x[0])
        time_L_index = fluxes[i].pruned_times.index(time_R)
        time_R_index = fluxes[i].pruned_times.index(time_L)
        
        # if both indices exist, set CH4 delta as the gap between the last entry before and first entry after the cut
        # this is for the sake of maintaining a linear relationship, it adds a fixed offset to each entry after the cut
        # if the cut is at the boundary of the data, the offset will be set to zero (i.e. the cut isn't in the middle of the data)
        if time_L_index and time_R_index:
            CH4_delta = fluxes[i].pruned_CH4[time_R_index] - fluxes[i].pruned_CH4[time_L_index]
        else:
            CH4_delta = 0

        # obtain time offset as the time elapsed by the cut
        # for the sake of maintaining a linear relationship, adds a fixed offset
        time_delta = time_R - time_L
        fluxes[i].cuts.append([time_R_index, time_L_index])

        times = []
        CH4 = []

        # if entry is not in the cut, add it to a new set
        for k in range(len(fluxes[i].pruned_times)):
            if fluxes[i].pruned_times[k] < time_L:
                times.append(fluxes[i].pruned_times[k])
                CH4.append(fluxes[i].pruned_CH4[k])
            if fluxes[i].pruned_times[k] > time_R:
                times.append(fluxes[i].pruned_times[k] - time_delta)
                CH4.append(fluxes[i].pruned_CH4[k] + CH4_delta)
          
        # update flux pruned sets with cut sets
        fluxes[i].pruned_times = times
        fluxes[i].pruned_CH4 = CH4

        # refresh the plot
        draw_plot(i, fluxes, fig, ax, cid)

    # if r key pressed, reset data
    if event.key == 'r':
        fluxes[i].pruned_times = fluxes[i].times
        fluxes[i].pruned_CH4 = fluxes[i].CH4
        fluxes[i].cuts = []
        draw_plot(i, fluxes, fig, ax, cid)
    
    # right arrow key moves to the next flux, or exits if currently on the last flux
    if event.key == 'right':
        if i == len(fluxes) - 1:
            plt.ioff()
            plt.close('all')
            return 0
        else:
            draw_plot(i + 1, fluxes, fig, ax, cid)
        
    # left arrow key moves to the previous flux, or does nothing if at the beginning
    if event.key == 'left':
        if i != 0:
            draw_plot(i - 1, fluxes, fig, ax, cid)


#draw plot for i-th flux
def draw_plot(i, fluxes, fig, ax, cid):

    fig.clear()
    ax = fig.add_subplot()
    
    plt.plot(fluxes[i].pruned_times, fluxes[i].pruned_CH4, linewidth = 2.0)
    line_L = draggable_lines(ax, 'v', fluxes[i].pruned_times[0], [fluxes[i].pruned_times[0], fluxes[i].pruned_times[-1]], plt.gca().get_ylim())   # left draggable boundary line
    line_R = draggable_lines(ax, 'v', fluxes[i].pruned_times[-1], [fluxes[i].pruned_times[0], fluxes[i].pruned_times[-1]], plt.gca().get_ylim())     # right draggable boundary line

    # if currently on the last flux, change header information, otherwise set title to user controls
    if i == len(fluxes) - 1:
        ax.set(title = fluxes[i].name +  "\nLast flux! Press right arrow to finish, enter to cut data, r to reset cuts\nUse the mouse to drag peak bounds")
    else:      
        ax.set(title = fluxes[i].name + '\nUse arrow keys to navigate fluxes, enter to cut data, r to reset cuts\nUse the mouse to drag cut bounds')

    ax.set(xlabel = "Time (s)")                 # x axis label
    ax.set(ylabel = "CH4 concentration (ppm)")  # y axis label
    fig.canvas.mpl_disconnect(cid)
    cid = fig.canvas.mpl_connect('key_press_event', lambda event: on_press(event, i, fluxes, line_L, line_R, fig, ax, cid))   # connect key press event  
    ax.grid(True)
    fig.canvas.draw()


# entry point for drawing the plots for the user to cut data
def prune(fluxes):
    i = 0
    fig, ax = plt.subplots()
    fig.set_size_inches(9,6)
    cid = ''
    plt.grid(True)
    plt.ion()
    draw_plot(i, fluxes, fig, ax, cid)
    plt.show(block=False)
    while plt.get_fignums():
        fig.canvas.draw_idle()
        fig.canvas.start_event_loop(0.05)



# performs linear regression to generate linear gas concentration rate of change per minute
def linear_model(fluxes, Vol, CO2_or_CH4):
    for flux in fluxes:
        X = flux.pruned_times
        Y = flux.pruned_CH4

        # simple linear regression
        sumX = sum(X)
        sumY = sum(Y)
        meanX = sumX/len(X)
        meanY = sumY/len(Y)

        SSx = 0 # sum of squares
        SP = 0  # sum of products

        for i in range(len(X)):
            SSx = SSx + (X[i] - meanX) ** 2
            SP = SP + (X[i] - meanX)*(Y[i] - meanY)

        # generates slope and intercept based on standards and baseline samples
        m = SP/SSx
        b = meanY - m * meanX

        SS_res = 0
        SS_t = 0

        for i in range(len(X)):
            SS_res = SS_res + (Y[i] - X[i]*m - b) ** 2
            SS_t = SS_t + (Y[i] - meanY) ** 2
        

        R2 = 1 - SS_res/SS_t    # coefficient of determination

        # calculates flux depending on CO2 vs. CH4
        flux.RSQ = R2
        flux.RoC = m * 60
        if CO2_or_CH4.lower() == "co2":
            flux.flux = (flux.RoC*(Vol/(0.0821*flux.temp))*(0.044*1440)/(math.pi*0.11*0.11)*(12/44)/1000)
        else:
            flux.flux = (flux.RoC*(Vol/(0.0821*flux.temp))*(0.016*1440)/(math.pi*0.11*0.11)*(12/16)/1000)


# calculates cut offsets for the sake of reporting
def offsets(fluxes):
    for flux in fluxes:

        flux.max_time = max(flux.pruned_times)
        flux.min_time = min(flux.pruned_times)

        # for each cut, rebuild pruned data sets with '' for cut indices
        cut_size = 0
        flux.data_loss = 100 - round(len(flux.pruned_times) / len(flux.times) * 100, 2)
        for cut in flux.cuts:
            for i in range(cut[0] + cut_size, cut[1] + 1 + cut_size):
                flux.pruned_times.insert(i, '')
                flux.pruned_CH4.insert(i, '')
            cut_size += cut[1] + cut[0] + 1

        # calculate the offset at each index
        for k in range(len(flux.times)):
            if flux.pruned_times[k] != '':
                flux.time_offsets.append(flux.times[k] - flux.pruned_times[k])
                flux.CH4_offsets.append(flux.CH4[k] - flux.pruned_CH4[k])
            else:
                flux.time_offsets.append(0)
                flux.CH4_offsets.append(0)


# outputs data to excel file
def outputData(fluxes, site, date, CO2_or_CH4, Vol):
    out = tkinter.filedialog.asksaveasfilename(defaultextension='.xlsx')
    workbook = xlsxwriter.Workbook(out)

    # summary worksheet, displays R^2, rate of change, flux, chamber volume, air temp for each flux
    worksheet = workbook.add_worksheet("Summary")
    worksheet.write_row(0, 0, ["Site:", site])
    worksheet.write_row(1, 0, ["Date:", date])
    if CO2_or_CH4.lower() == "co2":
        worksheet.write_column(3, 0, ["Flux name", '', "Chamber volume (L)", "Air temp (K)", '',  "RSQ", "Rate of change (CO2 [ppm/min])", "Flux of CO2 (g C m^-2 d^-1", "Data loss (%)"])
    else:
        worksheet.write_column(3, 0, ["Flux name", '', "Chamber volume (L)", "Air temp (K)", '', "RSQ", "Rate of change (CH4 [ppm/min])", "Flux of CH4 (g C m^-2 d^-1", "Data loss (%)"])
    for i in range(len(fluxes)):
        worksheet.write_column(3, i + 1, [fluxes[i].name , '', Vol, fluxes[i].temp, '', fluxes[i].RSQ, fluxes[i].RoC, fluxes[i].flux, fluxes[i].data_loss])
        worksheet.set_column(i + 1, i + 1, len(fluxes[i].name ))
    worksheet.set_column(0, 0, len("Rate of change (CH4 [ppm/min])"))
    
    # create page for each flux, pages give a detailed breakdown of each fluxes data sets as well as the values that have been cut
    worksheets = {}
    for flux in fluxes:
        if flux.name not in worksheets:
            worksheet = workbook.add_worksheet(flux.name)
            worksheets[flux.name] = 1
        else:
            worksheets[flux.name] += 1
            worksheet = workbook.add_worksheet(flux.name + " (%s)" %(str(worksheets[flux.name])))
        worksheet.write_row(0, 0, ["Name", flux.name])
        worksheet.write_row(1, 0, ["RSQ", flux.RSQ, '', '', "Chamber volume (L)", Vol])
        worksheet.write_row(2, 0, ["Rate of change (CH4 [ppm/min]", flux.RoC, '', '', "Air temp (K)", flux.temp])
        if CO2_or_CH4.lower() == 'co2':
            worksheet.write_row(3, 0, ["Flux of CO2 (g C m^-2 d^-1", flux.flux])
        else:
            worksheet.write_row(3, 0, ["Flux of CH4 (g C m^-2 d^-1", flux.flux])
        worksheet.write_row(4, 0, ["Data loss (%)", flux.data_loss])

        worksheet.write(6, 0, "Original times (s)")
        worksheet.set_column(0, 0, len("Rate of change (CH4 [ppm/min])"))
        worksheet.write(6, 1, "Pruned times (s)")
        worksheet.set_column(1, 1, len("Pruned times (s)"))
        worksheet.write(6, 2, "Time offsets (s)")
        worksheet.set_column(2, 2, len("Time offsets (s)"))

        if CO2_or_CH4.lower() == "co2":
            worksheet.write(6, 4, "Original CO2 concentrations (ppm)")
            worksheet.set_column(4, 4, len("Original CO2 concentrations (ppm)"))
            worksheet.write(6, 5, "Pruned CO2 concentrations (ppm)")
            worksheet.set_column(5, 5, len("Pruned CO2 concentrations (ppm)"))
            worksheet.write(6, 6, "CO2 concentration offsets (ppm)")
            worksheet.set_column(6, 6, len("CO2 concentration offsets (ppm)"))
        else: 
            worksheet.write(6, 4, "Original CH4 concentrations (ppb)")
            worksheet.set_column(4, 4, len("Original CH4 concentrations (ppb)"))
            worksheet.write(6, 5, "Pruned CH4 concentrations (ppb)")
            worksheet.set_column(5, 5, len("Pruned CH4 concentrations (ppb)"))
            worksheet.write(6, 6, "CH4 concentration offsets (ppb)")
            worksheet.set_column(6, 6, len("CH4 concentration offsets (ppb)"))

        for i in range(len(flux.times)):
            worksheet.write_row(i + 7, 0, [flux.times[i], flux.pruned_times[i], flux.time_offsets[i], '', flux.CH4[i], flux.pruned_CH4[i], flux.CH4_offsets[i]])

        # generate chart showing cut values compared to kept values with offsets
        chart = workbook.add_chart({'type': 'line'})
        chart.add_series({'values' : '=\'%s\'!E8:E%i'%(flux.name, len(flux.times) + 9), 'categories' : '=\'%s\'!A8:A%i'%(flux.name, len(flux.CH4) + 9), 'name': 'Cut values', 'line': {'color': 'red'}})
        chart.add_series({'values' : '=\'%s\'!F8:F%i'%(flux.name, len(flux.times) + 9), 'categories' : '=\'%s\'!A9:A%i'%(flux.name, len(flux.CH4) + 9), 'name': 'Kept values', 'line': {'color': 'green'}})
        if CO2_or_CH4.lower() == "co2":
            chart.set_x_axis({'interval_unit': 10, 'interval_tick': 2, 'name': 'CO2 concentraion (ppm)'})
        else:
            chart.set_x_axis({'interval_unit': 10, 'interval_tick': 2, 'name': 'CH4 concentraion (ppb)'})
        chart.set_y_axis({'name': 'Time (s)'})
        chart.set_title({'name' : 'Concentraion vs. Time'})
        chart.set_size({'width': 800, 'height': 600})
        worksheet.insert_chart('I8', chart)
    
    workbook.close()    
    return out


#########################################################################################################################
######################################## script execution starts here! ##################################################
#########################################################################################################################


if __name__ == "__main__":

    os.system('cls' if os.name == 'nt' else 'clear')
    print("================================================================================")
    print("========================== LICOR data processing tool ==========================")
    print("================================================================================\n")
    
    # get field data and LICOR data files from user prompts
    root = tkinter.Tk()
    root.withdraw()
    print("Choose field data file:")
    field_data = tkinter.filedialog.askopenfilename(title = "Choose field data file")
    print("Choose LICOR data file:")
    licor_data = tkinter.filedialog.askopenfilename(title = "Choose LICOR data file")

    # prompt user to enter whether CO2 or CH4 flux is to be analyzed
    CO2_or_CH4 = ''
    while CO2_or_CH4.lower() != 'co2' and CO2_or_CH4.lower() != 'ch4':
        CO2_or_CH4 = input("Which flux to measure? (type \"CO2\" or \"CH4\"): ")
    
    # prompt user for chamber volume
    good_vol = False
    while good_vol == False:
        try:
            Vol = float(input("Enter chamber volume in Litres: "))
        except ValueError:
            print("Error: not a number!")
        else:
            good_vol = True

    # prompt user for site name
    site = input("Enter the site name: ")

    #prompt user for site date
    date = input("Enter the site date: ")

    fluxes = input_data(field_data, licor_data, CO2_or_CH4)
    prune(fluxes)
    linear_model(fluxes, Vol, CO2_or_CH4)
    offsets(fluxes)
    out = outputData(fluxes, site, date, CO2_or_CH4, Vol)

    x = input("Finished! Results have been outputted to " + out + ". Press enter to exit: ")
