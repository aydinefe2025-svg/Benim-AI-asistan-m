#include <stdio.h>
#include <math.h>
#include <assert.h>
#include "split_quad.h"
int main(void){double v[1002];int count=0;double oldmax=0,newmax=0;for(int n=11;n<=401;n+=10){double h=1./(n-1);for(int s=2;s<n;s++){double x=(s-1)*h;for(int k=1;k<=n;k++)v[k]=fabs((k-1)*h-x);double exact=.5*(x*x+(1-x)*(1-x)),old=0;for(int k=1;k<=n-2;k+=2)old+=h/3*(v[k]+4*v[k+1]+v[k+2]);double err=fabs(jq_split(v,n,s,h)-exact);if(err>newmax)newmax=err;if(fabs(old-exact)>oldmax)oldmax=fabs(old-exact);assert(err<3e-14);count++;}}printf("%d exact kink tests; old max %.17g new max %.17g\n",count,oldmax,newmax);}
