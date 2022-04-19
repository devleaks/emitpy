import logging
from geojson import Feature, Point

from emitpy.airspace import XPAirspace, FlightPlanRoute
from emitpy.parameters import MANAGED_AIRPORT

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("Flightplan-Route")


def main():

    a = XPAirspace()
    logger.debug("loading..")
    a.load()
    logger.debug("..done")

    fpb = FlightPlanRoute(
        managedAirport=MANAGED_AIRPORT["ICAO"],
        fromICAO="LTAC",
        toICAO="OTHH")

    fpb.setAirspace(a)

    plan = fpb.getFlightPlan()
    print(plan)

main()


"""
Little Navmap gives the following path:

Identifiant;Région;Nom;Procédure;Voie Aérienne ou Procédure;Restriction ft/kts;Type;Fréquence MHz/kHz/Cha.;Portée Nm;Route °M;Course °T;Distance Nm;Restant Nm;Durée Segment hh:mm;ETA hh:mm;Carburant Dispo en lbs;Carburant Dispo en gal;Vent °M kts;Vent de Face/Arrière kts;Altitude ft;Remarques;Longitude;Latitude
BIBOS;EB;;Départ;;;;;;;;0,0;2 773;;;;;;;;;4,27358341;50,47719574
BUPAL;EB;;;;;;;;38;40;19,3;2 754;;;;;;;;;4,60111094;50,72305679
REMBA;EB;;;UL607 / J;19 500;;;;105;107;12,4;2 741;;;;;;;;;4,91402769;50,66222382
SPI;EB;Sprimont;;UL607 / J;19 500;VORDME (H);113,10;130;107;108;28;2 713;;;;;;;;;5,62361097;50,51472092
PELIX;EB;;;UL607 / J;24 500;;;;100;101;5,4;2 707;;;;;;;;;5,76249981;50,49694443
OSLUM;EB;;;UZ210 / J;27 000;;;;123;125;24;2 683;;;;;;;;;6,27500010;50,26777649
LIRSU;ED;;;UZ210 / J;27 000;;;;123;125;8,4;2 675;;;;;;;;;6,45333338;50,18666840
NOSPA;ED;;;UZ210 / J;27 000;;;;133;135;14,1;2 661;;;;;;;;;6,71138906;50,02055740
KRH;ED;Karlsruhe;;UZ210 / J;27 000;VORDME (H);115,95;130;127;129;96;2 565;;;;;;;;;8,58423615;48,99294281
LAMGO;ED;;;UM150 / J;24 500;;;;128;130;10,0;2 555;;;;;;;;;8,77916622;48,88583374
UTABA;ED;;;UM150 / J;24 500;;;;141;144;47;2 509;;;;;;;;;9,46166706;48,25500107
MOMUK;ED;;;UL607 / J;24 500;;;;136;139;33;2 476;;;;;;;;;9,99694443;47,83861160
BEMKI;ED;;;UL607 / J;24 500;;;;140;143;21;2 455;;;;;;;;;10,30559444;47,55938721
XEBIX;LO;;;UL607 / J;24 500;;;;140;143;11,9;2 443;;;;;;;;;10,47987461;47,40001297
ELMEM;LO;;;UL607 / J;24 500;;;;148;152;7,8;2 435;;;;;;;;;10,57073879;47,28563309
BILDU;LO;;;UN606 / J;24 500;;;;148;152;7,8;2 427;;;;;;;;;10,66178036;47,17044449
OTRES;LO;;;UN606 / J;24 500;;;;156;160;9,4;2 418;;;;;;;;;10,74236965;47,02346802
GIRIS;LO;;;UN606 / J;24 500;;;;156;159;16,2;2 402;;;;;;;;;10,88412189;46,77178192
TISAX;LI;;;N606 / B;19 000-33 500;;;;132;135;10,6;2 391;;;;;;;;;11,06499958;46,64527893
NAXAV;LI;;;N606 / B;19 000-33 500;;;;132;136;15,2;2 376;;;;;;;;;11,32222176;46,46389008
NIVAS;LI;;;N606 / J;29 000-33 500;;;;126;130;52;2 324;;;;;;;;;12,28138924;45,90000153
BADOP;LI;;;N606 / J;29 000-33 500;;;;127;131;40;2 284;;;;;;;;;13,00416660;45,46222305
BABAG;LI;;;N606 / J;29 000-33 500;;;;127;131;6,9;2 277;;;;;;;;;13,12694454;45,38694382
PEVAL;LD;;;UN606 / J;28 500-33 500;;;;128;132;6,8;2 270;;;;;;;;;13,24750042;45,31138992
NAKIT;LD;;;UN606 / J;28 500-32 500;;;;127;131;11,2;2 259;;;;;;;;;13,44777775;45,18805695
PUL;LD;Pula;;UN606 / J;28 500-32 500;VORDME (H);111,25;130;128;131;27;2 232;;;;;;;;;13,91811943;44,89236832
DOLOM;LD;;;UL614 / J;28 500-32 500;;;;102;105;42;2 190;;;;;;;;;14,87611103;44,70722198
PALEZ;LD;;;UL614 / J;28 500-32 500;;;;101;106;29;2 160;;;;;;;;;15,53305531;44,57500076
SONIK;LD;;;UL614 / J;28 500-32 500;;;;102;106;27;2 133;;;;;;;;;16,14333344;44,44833374
ELTIB;LQ;;;UL614 / J;28 500-32 500;;;;102;107;30;2 103;;;;;;;;;16,81638908;44,30361176
SOLGU;LQ;;;UL614 / J;28 500-32 500;;;;102;107;38;2 065;;;;;;;;;17,66138840;44,11583328
KEB;LQ;Sarajevo;;UL614 / J;28 500-32 500;VORDME (H);116,70;130;106;108;36;2 029;;;;;;;;;18,44982719;43,93386459
MITNO;LQ;;;UL614 / J;28 500-32 500;;;;103;105;36;1 994;;;;;;;;;19,24166679;43,77333450
PESAK;LQ;;;UL614 / J;28 500-32 500;;;;101;106;11,8;1 982;;;;;;;;;19,50416756;43,71861267
TORTO;LY;;;UL614 / J;28 500-32 500;;;;101;106;10,3;1 972;;;;;;;;;19,73130608;43,67086029
RAMAP;LY;;;UL614 / J;28 500-32 500;;;;101;106;53;1 919;;;;;;;;;20,89111137;43,41836166
GINAM;LY;;;UL614 / J;28 500-32 500;;;;102;107;22;1 897;;;;;;;;;21,37636185;43,30855560
NISVA;LY;;;UL614 / J;28 500-32 500;;;;102;107;65;1 831;;;;;;;;;22,79750061;42,97277832
USALI;LB;;;N131 / B;11 000;;;;132;137;55;1 776;;;;;;;;;23,64555550;42,30194473
OTKOK;LB;;;N131 / B;11 500;;;;133;138;24;1 752;;;;;;;;;24,01250076;41,99944305
RODIP;LB;;;N131 / B;11 500;;;;133;138;46;1 705;;;;;;;;;24,70111084;41,42083359
IDILO;LG;;;UN131 / J;24 500-46 000;;;;133;138;50;1 655;;;;;;;;;25,43944359;40,79055405
BELGI;LT;;;UN131 / J;24 500-46 000;;;;125;131;27;1 628;;;;;;;;;25,88333321;40,50000000
KONEN;LT;;;UT38 / J;28 500;;;;117;122;76;1 552;;;;;;;;;27,27722168;39,81166840
ATKAN;LT;;;UT38 / J;28 500;;;;118;123;32;1 520;;;;;;;;;27,84944534;39,52000046
KUDAK;LT;;;UT38 / J;28 500;;;;118;124;24;1 496;;;;;;;;;28,27666664;39,29888916
TUMER;LT;;;UT38 / J;28 500;;;;118;124;67;1 429;;;;;;;;;29,47027779;38,66555405
RESLI;LT;;;UT38 / J;28 500;;;;120;126;38;1 391;;;;;;;;;30,11972237;38,29444504
LEMDA;LT;;;UT38 / J;28 500;;;;121;126;32;1 360;;;;;;;;;30,65694427;37,98222351
KETEK;LT;;;UT38 / J;28 500;;;;121;127;109;1 251;;;;;;;;;32,47833252;36,88777924
VESAR;LT;;;UT38 / J;28 500;;;;122;128;94;1 156;;;;;;;;;34,01610947;35,91555405
NIKAS;LC;;;UW10 / J;24 500;;;;112;117;94;1 063;;;;;;;;;35,71666718;35,19333267
07BAN;OS;;;R785 / B;29 000;;;;75;80;5,2;1 057;;;;;;;;;35,82110977;35,20777893
BAN;OS;Banias;;R785 / B;29 000;NDB;304,0;;74;80;6,8;1 051;;;;;;;;;35,95792007;35,22828674
BRAVO;OS;;;R785 / B;29 000;;;;128;133;47;1 004;;;;;;;;;36,65301132;34,69304276
KTN;OS;Kariatain;;R785 / B;29 000;VORDME (L);117,70;40;130;133;42;962;;;;;;;;;37,26420975;34,21328354
BASEM;OS;;;R785 / B;29 000;;;;151;154;44;918;;;;;;;;;37,65194321;33,56027603
ABBAS;OS;;;R785 / B;29 000;;;;149;154;8,5;910;;;;;;;;;37,72499847;33,43333435
ZELAF;OJ;;;R785 / B;29 000;;;;150;155;32;878;;;;;;;;;37,99979401;32,94894409
KAREM;OJ;;;UR785 / B;24 000;;;;149;154;6,4;871;;;;;;;;;38,05677032;32,85289001
RASLI;OJ;;;UR785 / B;24 000;;;;149;153;63;808;;;;;;;;;38,61333466;31,90666580
TOMDA;OE;;;UP559 / B;16 000-46 000;;;;149;154;14,2;794;;;;;;;;;38,73466873;31,69332695
KAVID;OE;;;UP559 / B;16 000-46 000;;;;126;131;100;694;;;;;;;;;40,19638824;30,59777832
GADLI;OE;;;UP559 / B;16 000-46 000;;;;114;119;26;667;;;;;;;;;40,63916779;30,38666725
DELNI;OE;;;UP559 / B;16 000-46 000;;;;115;119;38;630;;;;;;;;;41,27416611;30,07999992
TOKLU;OE;;;UP559 / B;16 000-46 000;;;;115;119;46;584;;;;;;;;;42,03888702;29,70361137
LUDEP;OE;;;UP559 / B;16 000-46 000;;;;116;120;65;519;;;;;;;;;43,11277771;29,16333389
RASMO;OE;;;UP559 / B;16 000-46 000;;;;116;120;25;494;;;;;;;;;43,52194595;28,95361137
LOTOK;OE;;;UP559 / B;16 000-46 000;;;;117;120;96;398;;;;;;;;;45,08666611;28,13249969
KMC;OE;King Saud Ab Hafr Al Batin;;UP559 / B;16 000-46 000;VORTAC (H);115,90;130;118;121;29;369;;;;;;;;;45,55569458;27,88058281
BOTEP;OE;;;UP559 / B;16 000-46 000;;;;100;103;37;332;;;;;;;;;46,24027634;27,73888969
DEBOL;OE;;;UN694 / B;16 000-46 000;;;;167;171;23;308;;;;;;;;;46,31206131;27,35445786
ALSAT;OE;;;UN685 / B;16 000-46 000;;;;99;103;66;242;;;;;;;;;47,52166748;27,10305595
EGNOV;OE;;;UN685 / B;16 000-46 000;;;;99;103;14,5;227;;;;;;;;;47,78694534;27,05027771
GEPAK;OE;;;UL681 / B;16 000-46 000;;;;117;121;59;169;;;;;;;;;48,72444534;26,54999924
DELMU;OE;;;UL681 / B;16 000-46 000;;;;125;128;23;146;;;;;;;;;49,05638885;26,31472206
ROSEM;OE;;;UL681 / B;16 000-46 000;;;;125;128;17,5;129;;;;;;;;;49,31111145;26,13277817
NADNO;OE;;;UL681 / B;16 000-46 000;;;;126;129;53;75;;;;;;;;;50,08333206;25,57527733
SALWA;OE;;;UL681 / B;16 000-46 000;;;;126;129;30;45;;;;;;;;;50,51333237;25,26055527
ULIKA;OB;;;UL681 / B;16 000-46 000;;;;86;89;7,3;38;;;;;;;;;50,64688492;25,26258087
GINTO;OT;;;UM430 / J;15 000-46 000;;;;86;89;23;14,9;;;;;;;;;51,07107925;25,26821136
EGMUR;OT;;Destination;;;;;;119;121;14,9;0,0;;;;;;;;;51,30514908;25,13951874

"""
