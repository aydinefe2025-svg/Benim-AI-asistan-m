/* Split a uniform-grid integral at the Green-kernel diagonal. Indices 1..N. */
static double jq_segment(const double *v,int a,int b,double h){
 int n=b-a,k; double q=0.;
 if(n<=0)return 0.;
 if(n==1)return .5*h*(v[a]+v[b]);
 if(n%2){q=3.*h/8.*(v[a]+3.*v[a+1]+3.*v[a+2]+v[a+3]);a+=3;}
 for(k=a;k+2<=b;k+=2)q+=h/3.*(v[k]+4.*v[k+1]+v[k+2]);
 return q;
}
static double jq_split(const double *v,int n,int s,double h){return jq_segment(v,1,s,h)+jq_segment(v,s,n,h);}
