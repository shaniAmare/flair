from __future__ import print_function

########################################################################
# File: ssPrep.py
#  executable: ssPrep.py
# Purpose: 
#
#          
# Author: Cameron M. Soulette
# History:      cms 05/01/2018 Created
#
########################################################################


########################################################################
# Hot Imports & Global Variable
########################################################################


import os, sys
from kerneltree import IntervalTree
import numpy as np
from tqdm import *


########################################################################
# CommandLine
########################################################################

class CommandLine(object) :
    '''
    Handle the command line, usage and help requests.
    CommandLine uses argparse, now standard in 2.7 and beyond. 
    it implements a standard command line argument parser with various argument options,
    and a standard usage and help,
    attributes:
    myCommandLine.args is a dictionary which includes each of the available command line arguments as
    myCommandLine.args['option'] 
    
    methods:
    
    '''
    
    def __init__(self, inOpts=None) :
        '''
        CommandLine constructor.
        Implements a parser to interpret the command line argv string using argparse.
        '''
        import argparse
        self.parser = argparse.ArgumentParser(description = ' ssPrep.py - a tool to leverage annotation and short read data to correct misaligned splice junctions in short read data.',
                                             epilog = 'Please feel free to forward any questions/concerns to /dev/null', 
                                             add_help = True, #default is True 
                                             prefix_chars = '-', 
                                             usage = '%(prog)s -i reads.bed -g annotations.gtf -j other_junctions.bed -o out_file.bed')
        # Add args
        self.parser.add_argument('-i', "--input_bed", action = 'store', required=True, help='Input reads in bed12 format.')
        self.parser.add_argument('-j', "--juncs",  action = 'store', required=True, help='KnownJunction.bed.')
        self.parser.add_argument('-w', '--wiggleWindow', action = 'store', type=int, required=False, default = 15, help='Splice site correction window flank size.')
        self.parser.add_argument('-o', "--output_fname", action = 'store', required=True, help='Output file name.')
        self.parser.add_argument('--correctStrand', action = 'store_true', required=False, default = False, help='Try to resolve read strand by using annotated splice site strand.')
        #self.parser.add_argument('--keepZero', action = 'store_true', required=False, default = False, help='Keep alignments with no spliced junctions (single exon txns).')
        
        
        if inOpts is None :
            self.args = vars(self.parser.parse_args())
        else :
            self.args = vars(self.parser.parse_args(inOpts))


########################################################################
# BED File
########################################################################

class BED12(object):
    '''
    Handles BED format file input and output.

    # BED12 has some built in functions
    # for formally defining elemnts of a bed12
    # and to preform coordinate conversions

    Attribute names are stable, but the value refreshes while iterating through
    the bed file.

    attributes:
    chrom, start, end, strand = reference aligment descriptors
    read = query/feature id
    score = integer 
    c1, c2 = (formally) describe where the open reading frame starts and stop
    exons, size, starts = bed12 alignment blocks descibing where the aligmnents matches in the reference.

    methods:
    getLine - gets line from bed file, and defines values for attributes
    bed12to(Juncs|Exons) - converts bed12 aligmnet blocks to reference coordinate positions

    getLine must be called before bed12to(Juncs|Exons) can be called since it relies on attributes defined in getLine.

    '''
    def __init__(self, fname=None):
        self.fname = fname
        
        if not os.path.isfile(fname):
            print("%s does not exist. Exiting.", file=sys.stderr)
            sys.exit(1)

    def getLine(self):

        with open(self.fname,'r') as entries:
            for entry in entries:
                cols = entry.rstrip().split()
                self.chrom, self.start, self.end, self.name = cols[0], int(cols[1]), int(cols[2]), cols[3]
                self.score, self.strand, self.c1, self.c2 = int(cols[4]), cols[5], int(cols[6]), int(cols[7])
                self.color, self.exons = cols[8], int(cols[9])  
                self.sizes =  [int(x) for x in cols[10].split(",")[:-1]] if cols[10][-1] == "," else [int(x) for x in (cols[10]+",").split(",")[:-1]]
                self.starts = [int(x) for x in cols[11].split(",")[:-1]] if cols[11][-1] == "," else [int(x) for x in (cols[11]+",").split(",")[:-1]]
                yield cols


    def bed12toJuncs(self):
        '''
        Take bed12 entry and convert block/sizes to junction coordinates.
        '''
        junctions = list()
        for num, st in enumerate(self.starts,0):

            if num+1 >= len(self.starts):
                break
            ss1 = self.start + st + self.sizes[num]
            ss2 = self.start + self.starts[num+1]
            junctions.append((ss1,ss2))

        return junctions


    def bed12toExons(self):
        '''
        Take bed12 entry and convert block/sizes to exon coordinates.
        '''
        exons = list()
        for num, st in enumerate(self.starts,0):
            c1 = self.start + st
            c2 = c1 + self.sizes[num]
            exons.append((c1,c2))
        return exons

########################################################################
# Read
########################################################################

class READ(object):
    '''
    Handles Read data.
    '''
    def __init__(self, rid=None, juncs=None, chrom=None):
        self.rid     = rid
        self.junctions = juncs
        self.chrom   = chrom

########################################################################
# Junc
########################################################################

class SS(object):
    '''
    Handles Junc data.
    '''
    def __init__(self, coord=None, strand=None, ssType=None):
        self.coord   = coord
        self.strand  = strand
        self.ssType  = ssType

        # Descriptive attributes.
        self.support = set()
        self.usage   = 0
        self.ssCorr  = None
        


########################################################################
# Functions
########################################################################

def juncsToBed12(start, end, coords):
    '''
    Take alignment start, end, and junction coords and convert to block/size bed12 format.
    start = integer
    end = integer
    coords = list formatted like so [(j1_left,j1_right),(j2_left,j2_right)]
    returns num_exons, sizes, starts
    '''
    sizes, starts = [],[]
    # initial start is 0
    if len(coords) > 0:
        for num,junc in enumerate(coords,0):
            ss1, ss2 = junc

            if num == 0:
                st = 0
                size = abs(start-ss1)
            else:
                st = coords[num-1][1] - start
                size =  ss1 - (st + start)
            starts.append(st)
            sizes.append(size)
        st = coords[-1][1] - start
        size =  end - (st + start)
        starts.append(st)
        sizes.append(size)
        return len(starts), sizes, starts
    else:
        return 1, [end-start], [0]





def ssCorrrect(c,strand,ssType,intTree,ssData):
    '''
    correct un-annotated splice sites.
    '''

    hits = intTree.search(c,c)
    
    if len(hits)<1:
        ss = SS(c,strand,None)
        ssData[c] = ss
        ss.ssCorr = ss
        return ssData
    else:

        distances = [abs(c-x[-1]) for x in hits]
        minVal    = min(distances)
        count     = distances.count(minVal)

        if count>1:
            ss = SS(c,strand,None)
            ss.ssCorr = ss
            ssData[c] = ss
            return ssData
        else:
            cCorr = hits[distances.index(minVal)][-1]
            ss = SS(c,strand,ssType)
            ss.ssCorr = ssData[cCorr]
            ssData[c] = ss
            return ssData



def correctReads(bed, intTree, ssData, filePrefix, correctStrand):
    ''' Builds read and splice site objects '''

    inconsistent = open("%s_inconsistent.bed" % filePrefix,'w')
    corrected = open("%s_corrected.bed" % filePrefix,'w')

    bedObj = BED12(bed)
    for line in bedObj.getLine():
        juncs  = bedObj.bed12toJuncs()
        strand = bedObj.strand 
        c1Type,c2Type = ("donor","acceptor") if strand == "+" else ("acceptor","donor")

        newJuncs  = list()
        ssTypes   = list()
        ssStrands = set()
        novelSS   = False

        for x in juncs:
            c1, c2 = x[0], x[1]
            if c1 not in ssData:
                ssData = ssCorrrect(c1,strand,c1Type,intTree,ssData)
            if c2 not in ssData:
                ssData = ssCorrrect(c2,strand,c2Type,intTree,ssData)

            c1Obj, c2Obj = ssData[c1], ssData[c2]

            c1Corr = ssData[c1].ssCorr.coord
            c2Corr = ssData[c2].ssCorr.coord
            
            ssTypes   = [ssData[c1].ssCorr.ssType ,ssData[c2].ssCorr.ssType]
            ssStrands.add(ssData[c1].ssCorr.strand)
            ssStrands.add(ssData[c2].ssCorr.strand)

            if None in ssTypes or ssTypes[0] == ssTypes[1]:
                # Either two donors or two acceptors or both none.
                novelSS = True

            newJuncs.append((c1Corr,c2Corr))        
        blocks, sizes, starts = juncsToBed12(bedObj.start,bedObj.end,newJuncs)
        
        if correctStrand:
            if len(ssStrands)>1:
                novelSS = True
            elif len(ssStrands) == 1:
                strand = list(ssStrands)[0]
            elif len(ssStrands) == 0:
                strand = strand

        # 0 length exons, remove them.
        minSize = min(sizes)
        if minSize == 0: novelSS = True


        if novelSS:
            print(bedObj.chrom, bedObj.start, bedObj.end, bedObj.name,
                    bedObj.score, strand, bedObj.c1, bedObj.c2, bedObj.color,
                    blocks, ",".join(map(str,sizes))+",", ",".join(map(str,starts))+",", sep="\t", file=inconsistent)
        else:
            
            print(bedObj.chrom, bedObj.start, bedObj.end, bedObj.name,
                    bedObj.score, strand, bedObj.c1, bedObj.c2, bedObj.color,
                    blocks, ",".join(map(str,sizes))+",", ",".join(map(str,starts))+",", sep="\t", file=corrected)
    corrected.close()
    inconsistent.close()

def buildIntervalTree(juncs, wiggle):
    ''' Builds read and splice site objects '''
    x = IntervalTree()
    data = dict()

    with open(juncs) as lines:
        for line in lines:
            cols     = line.rstrip().split()
            c1, c2   = int(cols[1]), int(cols[2])
            strand   = cols[-1]
            annoType = cols[3]
            c1Type,c2Type = ("donor","acceptor") if strand == "+" else ("acceptor","donor")


            # add c1 first
            if c1 not in data:
                ss = SS(c1,strand,c1Type)
                ss.support.add(annoType)
                ss.ssCorr = ss
        
                # SS window
                c1S, c1E = c1-wiggle, c1+wiggle
                
                # Add to tree and object to data
                data[c1] = ss
                x.add(c1S,c1E,c1)

            else:
                data[c1].support.add(annoType)

            # now add c2
            if c2 not in data:
                ss = SS(c2,strand,c2Type)
                ss.support.add(annoType)
                ss.ssCorr = ss
        
                # SS window
                c2S, c2E = c2-wiggle, c2+wiggle
                
                # Add to tree and object to data
                data[c2] = ss
                x.add(c2S,c2E,c2)
            else:
                data[c2].support.add(annoType)

    return x, data

def main():
    '''
    maine
    '''

    # Command Line Stuff...
    myCommandLine = CommandLine()
    bed           = myCommandLine.args['input_bed']
    knownJuncs    = myCommandLine.args['juncs']
    
    wiggle        = myCommandLine.args['wiggleWindow']
    out           = myCommandLine.args['output_fname']

    resolveStrand = myCommandLine.args['correctStrand']

    # Build interval tree of known juncs
    intTree, ssData = buildIntervalTree(knownJuncs, wiggle)

    # Build read objects.
    correctReads(bed, intTree, ssData, out, resolveStrand)

            


if __name__ == "__main__":
    main()
