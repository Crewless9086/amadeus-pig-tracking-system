# ToDoList 2026-06-30 Live App Review Notes

Source: `planning/ToDoList.md`

Status: converted into CHARLIE mission queue records on 2026-06-30.

Created missions:

- `CHARLIE-MISSION-B825DC2E19036F92` - Review dashboard herd outcomes and order data
- `CHARLIE-MISSION-957B84CAE279032A` - Improve pig list width and interaction
- `CHARLIE-MISSION-EC639ABADF90FA97` - Review sales availability purpose and UI
- `CHARLIE-MISSION-08EA8ECB1F1F67D5` - Review orders list data migration and width
- `CHARLIE-MISSION-DD699F56DA9AB076` - Review manual new order workflow in AI sales system
- `CHARLIE-MISSION-41B5AC4170C855BA` - Fix litter stillborn birth-count mismatch logic

## Raw Notes Preserved

```text
https://amadeus-pig-tracking-system.onrender.com/ review results
- On the dashboard the tile HERD has a section at the bottom of it called "Outcomes This Month" and these are all showing 0, butI'm sure we had some died this months so perhaps worth checking these are getting the data from Supabase?
- The tile ORDERS is not showing anything, I do beleieve we had two test leads I was working showing so can we just check this, it's okay if the test is not showing but at least I do hope this is connected?
https://amadeus-pig-tracking-system.onrender.com/pigs this view is still narrow and I think the UI can be better, can we make this wider and display it better, perhaps like when you hover over the pig tile you get a little box with more important detail showing, I need it to be more interactive and just nice and easy to use. Perhaps same as the other pages we have a little totals on the top which will best work for us and then we can also add a filter that is worth it.
https://amadeus-pig-tracking-system.onrender.com/sales-availability this view can also become wider for the dashboard and the also I think we can improve it and make it better you have to scroll down alot and it's not as user friendly as I would think and also not very good for what it meant to do. I think we need to improve the UI and make it better and user friendlier. Also you will see it's showing records of pigs not longer on the faarm, this page was design for when we did only "Live stock Sales" but I'm not sure how useful this is now. We still will need to do "Live stock sales" but this is not yet set up with the new application. Open to suggestions. 
https://amadeus-pig-tracking-system.onrender.com/orders this view can also become wider for the dashboard but it's also not showing any data at the moment did this migrate? Or is there just no orders in here?
https://amadeus-pig-tracking-system.onrender.com/orders/new this can also be wider for the dashboard, and I think this was meant for "Live Stock sales" and it ws build and set up but when creating a manual , well this is not meant to happen as SAM is meant to deal with this but I guess having this as an options is always good just incase you have to created one. Not sure how this will work in our AI driven system. 
https://amadeus-pig-tracking-system.onrender.com/litters this can be wider for the dashboard, I also noticed the commen mistake. It's saying that there is and alrt on litter: LIT-2026-1025 "birth count mismatch" but it does not account for stillborns. This is the thing, Born alive is the amount born alive, total born is how many came out, if there was still borns they would be added to the still born column and the total born and (stillborn and born alive) should then match. then same goes for when adding the litter and we add still borns the system mark them as stillborn and they are marked dead and all the related columns are filled in. We keep trecords but they are not around. 
```
