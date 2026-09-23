###Ride The Wave

The goal of this project is to set up a relatively simople trading bot with the help of the Alpaca API with the Paper Trading account set up called Ride The Wave.

The intuition behind the bot is pretty simple but should be effective at a very basic level but guarantee positive gains regularly. 

The strategy is as follows:

1. Retrieve stock price data en masse at open or whenever the bot is turned on, and observe trends of tickers.

2. Select stocks which are growing in value in a consecutive period of time. If it is green for a certain set threshold time value set, put in an order for the stock. Mind you, the stock should only be bought if we see growth. in value in a set of time before putting in the order.

3. Once the order is put in, monitor the trend for a set threshold value time period for stocks bought. 

4. The waiting period here when we hold the stock is what I want to call the "Ride The Wave" period, where we are trying to ride on the profits of the stock.

5. If the stock price starts going down from a peak, then we have to sell the stock such that we retain a marginal gain based on the initial price we put the order in for even when the stock starts going down.

6. At the end of the set bot run period or end of the day of trading, consolidate profits we have made on stock sales and existing stocks we are still holding. For the next day use a certain percentage of the gains we made on stock sales for reinvestment on this same strat.

This is the raw gist of what I want to accomplish. I defintiely want make this very very robust moving forward adding much more complex strategies that the Alpaca APi can offer, utilize my personal machine to execute trades a bit faster, etc. but within the tecnical limits of my machine.

I would also like a simulation suite to see how a strategy might have performed in the past days, when I did not run the strategy. 

I would like detailed architecture for this on what kind of approach we should take to execute the above mentioned strategy, reasoning behind the architecture, all in a preferably easy to read format but explaining technical decisions well. I want basic documentation on API's that will be used, with sample responses in documentation as well.

I want a UI which is clear and not messy, has the stocks bought displayed, price at buy, current price, profits, etc. that one would expect when they develop trading apps.

For every feature built I want documentation in plain english that someone with my background would understand.

Also this computer is very new, so I will need to install a lot of dependencies as well. if you can create a requirements document, I will start making you env ready for testing that you will do as you build the app.

###IMPORTANT MAINTAIN A CLAUDE.MD TO KEEP TRACK AT ALL TIMES. MAINTAIN PROPER FOLDER STRUCTURE FOR THIS AND MD FILES IN FOLDERS TO TELL WHAT IS IN EACH FOLDER###